import time
import copy
import html
import json
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from app.db.session import Base, engine, get_db, initialize_schema
from app.models import models  # noqa: F401 ensures models are registered
from app.core.config import settings
from app.runtime.paper import paper_status
from app.analytics.performance import account_performance
from app.brokers.robinhood_oauth import (BrokerOAuthConfigurationError, connection_status,
    finish_connection, start_connection)
from app.brokers.robinhood_mcp import RobinhoodMcpError, discover_capabilities
from app.brokers.robinhood_adapter import verify_agentic_readiness, load_agentic_read_only_adapter
from app.brokers import etrade_connection
from app.brokers.etrade_adapter import ETradeError
from app.brokers import alpaca_connection
from app.security.dashboard import (require_dashboard_access, dashboard_access_granted,
                                    issue_dashboard_session)
from app.dashboard_html import DASHBOARD_HTML
from app.strategies.stage_runner import STAGE_RUNNER_VERSION
from app.services.live_readiness import report as live_readiness_report
from app.services.state_machine import StateManager
from app.audit.logger import log_and_commit
from app.markets.capabilities import CapabilityRegistry
from app.markets.account_capabilities import account_approval_report
from app.markets.options_research import assess_option_chain
from app.runtime.market_research_worker import (run_scan as run_market_research_scan,
                                                run_equity_scan as run_equity_research_scan,
                                                run_expanded_equity_scan)
from app.strategies.daily_trend_pullback import DailyTrendPullback, BroadDailyTrendPullback
from app.strategies.daily_trend_pullback import BROAD_UNIVERSE
from app.research.daily_trend_portfolio import STOP_LOSS, TAKE_PROFIT
from app.research.intraday_trend_pullback import STRATEGY_VERSION as INTRADAY_RESEARCH_VERSION

initialize_schema(engine)

app = FastAPI(title="Veloikos Trading", version="1.0.0")
from app.binance_routes import router as binance_router
app.include_router(binance_router)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")

STAGE_SYMBOLS = ("TQQQ",)  # Stage Runner instrument shown first in the terminal.
MARKET_CONTEXT_ETFS = ("FXI", "EWU")  # US-listed China/UK exposure, not local exchange quotes.
CRYPTO_CONTEXT = ("BTC/USD", "ETH/USD", "SOL/USD")  # Read-only market data for charts and tape.


@app.get("/terminal/market", dependencies=[Depends(require_dashboard_access)])
def terminal_market(symbol: str = Query(default="SPY", min_length=1, max_length=10),
                    timeframe: str = Query(default="5Min", pattern="^(1Min|5Min|15Min|1Day)$"),
                    db: Session = Depends(get_db)):
    """Read-only IEX quote and bounded intraday or daily candles for the terminal."""
    symbol = symbol.upper()
    symbol = {c.replace("/", ""): c for c in CRYPTO_CONTEXT}.get(symbol, symbol)  # BTCUSD position -> BTC/USD
    if symbol not in CRYPTO_CONTEXT and not symbol.replace(".", "").isalpha():
        raise HTTPException(status_code=400, detail="invalid symbol")
    try:
        adapter, _ = alpaca_connection.load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        end = now.isoformat().replace("+00:00", "Z")
        days = {"1Min": 1, "5Min": 3, "15Min": 7, "1Day": 90}[timeframe]
        start = (now - timedelta(days=days)).isoformat().replace("+00:00", "Z")
        if symbol in CRYPTO_CONTEXT:
            snapshot = adapter._request("GET", "/v1beta3/crypto/us/snapshots", data_api=True,
                                        params={"symbols": symbol}).get("snapshots", {}).get(symbol, {})
            item = snapshot.get("latestQuote") or {}
            trade = snapshot.get("latestTrade") or {}
            age = max(0, (now - datetime.fromisoformat(item["t"].replace("Z", "+00:00"))).total_seconds())
            raw = adapter._request("GET", "/v1beta3/crypto/us/bars", data_api=True, params={
                "symbols": symbol, "timeframe": timeframe, "start": start, "end": end, "limit": 10000,
            })
            bars = [{"timestamp": row["t"], "open": float(row["o"]), "high": float(row["h"]),
                     "low": float(row["l"]), "close": float(row["c"]), "volume": float(row["v"])}
                    for row in raw.get("bars", {}).get(symbol, [])]
            quote = {"bid": float(item["bp"]), "ask": float(item["ap"]),
                     "last": float(trade["p"]) if trade.get("p") is not None else None,
                     "age_seconds": age, "provider": "alpaca_crypto_us"}
        else:
            broker_quote = next(q for q in adapter.get_quotes([symbol]) if q.symbol == symbol)
            quote = {"bid": broker_quote.bid, "ask": broker_quote.ask,
                     "last": broker_quote.last if broker_quote.bid > 0 and broker_quote.ask > 0 else None,
                     "age_seconds": broker_quote.age_seconds, "provider": broker_quote.provider}
            bars = (adapter.get_daily_bars(symbol, start, end) if timeframe == "1Day"
                    else adapter.get_intraday_bars(symbol, start, end, timeframe=timeframe))
        return {"symbol": symbol, "quote": quote,
                "timeframe": timeframe, "source": "Alpaca Crypto US" if symbol in CRYPTO_CONTEXT else "Alpaca IEX", "as_of": end,
                "bars": bars[-120:]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"market data unavailable: {type(exc).__name__}") from exc


def _stream_credentials() -> tuple[str, str]:
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        adapter, _ = alpaca_connection.load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
        return adapter.headers["APCA-API-KEY-ID"], adapter.headers["APCA-API-SECRET-KEY"]


_market_stream = None


def market_stream():
    global _market_stream
    if _market_stream is None:
        from app.services.market_stream import MarketStream
        _market_stream = MarketStream(_stream_credentials)
    return _market_stream


@app.get("/terminal/stream", dependencies=[Depends(require_dashboard_access)])
async def terminal_stream(request: Request, symbols: str = Query(default="", max_length=400)):
    """Server-Sent Events: real-time IEX trade prints and minute bars (read-only, no keys)."""
    import asyncio
    from fastapi.responses import StreamingResponse
    stream = market_stream()
    wanted = set(stream.want([s for s in symbols.split(",") if s][:30]))
    queue = stream.listen()

    async def events():
        try:
            hello = {"type": "status", "status": stream.status, "error": stream.error, "symbols": sorted(wanted),
                     "last": {s: stream.last[s] for s in wanted if s in stream.last}}
            yield f"data: {json.dumps(hello)}\n\n"
            last_status = stream.status
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    if stream.status != last_status:
                        last_status = stream.status
                        yield f"data: {json.dumps({'type': 'status', 'status': stream.status, 'error': stream.error})}\n\n"
                    else:
                        yield ": keep-alive\n\n"
                    continue
                if event.get("symbol") in wanted:
                    yield f"data: {json.dumps(event)}\n\n"
        finally:
            stream.unlisten(queue)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


_ticker_cache: dict[str, object] = {"expires_at": 0.0, "payload": None}


@app.get("/terminal/ticker", dependencies=[Depends(require_dashboard_access)])
def terminal_ticker(db: Session = Depends(get_db)):
    """One read-only IEX snapshot batch for the exact live strategy universe."""
    if time.time() < _ticker_cache["expires_at"] and _ticker_cache["payload"] is not None:
        return _ticker_cache["payload"]
    try:
        adapter, _ = alpaca_connection.load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
        raw = adapter._request("GET", "/v2/stocks/snapshots", data_api=True,
                               params={"symbols": ",".join(STAGE_SYMBOLS + BROAD_UNIVERSE + MARKET_CONTEXT_ETFS), "feed": "iex"})
        now = datetime.now(timezone.utc)
        items = []
        for symbol in STAGE_SYMBOLS + BROAD_UNIVERSE + MARKET_CONTEXT_ETFS:
            snap = raw.get(symbol) or {}
            quote, trade = snap.get("latestQuote") or {}, snap.get("latestTrade") or {}
            previous = snap.get("prevDailyBar") or {}
            price, previous_close = trade.get("p"), previous.get("c")
            try:
                price = float(price) if price is not None else None
                previous_close = float(previous_close) if previous_close is not None else None
                quote_age = max(0, (now - datetime.fromisoformat(quote["t"].replace("Z", "+00:00"))).total_seconds()) if quote.get("t") else None
                trade_age = max(0, (now - datetime.fromisoformat(trade["t"].replace("Z", "+00:00"))).total_seconds()) if trade.get("t") else None
            except (KeyError, TypeError, ValueError):
                quote_age = trade_age = None
            items.append({"symbol": symbol, "asset_class": "ETF" if symbol in BROAD_UNIVERSE[:5] + MARKET_CONTEXT_ETFS else "stock",
                          "in_strategy_universe": symbol in BROAD_UNIVERSE or symbol in STAGE_SYMBOLS, "source": "Alpaca IEX",
                          "price": price, "previous_close": previous_close,
                          "change_pct": round((price / previous_close - 1) * 100, 2)
                                        if price is not None and previous_close and previous_close > 0 else None,
                          "bid": quote.get("bp"), "ask": quote.get("ap"),
                          "quote_age_seconds": quote_age, "trade_age_seconds": trade_age})
        try:
            crypto = adapter._request("GET", "/v1beta3/crypto/us/snapshots", data_api=True,
                                      params={"symbols": ",".join(CRYPTO_CONTEXT)}).get("snapshots", {})
        except Exception:
            crypto = {}  # Equity ticker remains usable if the crypto feed fails.
        for symbol in CRYPTO_CONTEXT:
            snap = crypto.get(symbol) or {}
            quote, trade = snap.get("latestQuote") or {}, snap.get("latestTrade") or {}
            previous = snap.get("prevDailyBar") or {}
            price = float(trade["p"]) if trade.get("p") is not None else None
            previous_close = float(previous["c"]) if previous.get("c") is not None else None
            try:
                quote_age = max(0, (now - datetime.fromisoformat(quote["t"].replace("Z", "+00:00"))).total_seconds())
                trade_age = max(0, (now - datetime.fromisoformat(trade["t"].replace("Z", "+00:00"))).total_seconds())
            except (KeyError, TypeError, ValueError):
                quote_age = trade_age = None
            items.append({"symbol": symbol, "asset_class": "crypto", "in_strategy_universe": False,
                          "source": "Alpaca Crypto US", "price": price, "previous_close": previous_close,
                          "change_pct": round((price / previous_close - 1) * 100, 2)
                                        if price is not None and previous_close and previous_close > 0 else None,
                          "bid": quote.get("bp"), "ask": quote.get("ap"),
                          "quote_age_seconds": quote_age, "trade_age_seconds": trade_age})
        payload = {"source": "Alpaca IEX + Crypto US", "as_of": now.isoformat(),
                   "universe": "daily-trend-pullback-broad-equity-etf-v1", "items": items}
        _ticker_cache.update(expires_at=time.time() + 20, payload=payload)
        return payload
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ticker data unavailable: {type(exc).__name__}") from exc

# The browser refreshes its display every second, but Alpaca account endpoints
# must not be called at browser-poll frequency.  This short process-local cache
# keeps the display live while reserving API capacity for the execution worker.
_live_portfolio_cache: dict[str, object] = {"expires_at": 0.0, "payload": None}
_LIVE_PORTFOLIO_CACHE_SECONDS = 5.0


@app.get("/market-capabilities", dependencies=[Depends(require_dashboard_access)])
def market_capabilities():
    """Public operator view of asset classes; this endpoint cannot enable one."""
    return {"capabilities": CapabilityRegistry().report()}


@app.get("/markets/catalog", dependencies=[Depends(require_dashboard_access)])
def market_catalog(asset_class: str = Query(default="us_equity", pattern="^(us_equity|crypto)$"),
                   db: Session = Depends(get_db)):
    """Expose broker-discoverable instruments as research coverage only.

    This route is read-only and deliberately reports ``research_only`` for
    every catalog result.  Broker availability is not execution authority.
    """
    try:
        adapter, _ = alpaca_connection.load_read_only_adapter(
            db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False
        )
        assets = adapter.list_active_assets(asset_class=asset_class)
        return {"asset_class": asset_class, "count": len(assets),
                "execution_status": "research_only",
                "assets": assets}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"market catalog unavailable: {type(exc).__name__}") from exc


@app.get("/market-capabilities/live-account", dependencies=[Depends(require_dashboard_access)])
def live_account_market_capabilities(db: Session = Depends(get_db)):
    """Read broker permissions without changing an execution gate."""
    try:
        adapter, paper = alpaca_connection.load_read_only_adapter(
            db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False
        )
        if paper:
            raise HTTPException(status_code=409, detail="stored credential is not live")
        account = adapter.get_account_capabilities()
        return {"broker_account": account, "approvals": account_approval_report(account),
                "capabilities": CapabilityRegistry().report(),
                "execution_note": "Broker approval alone does not enable an asset class for execution."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"live account capability unavailable: {type(exc).__name__}")


@app.get("/research/options/chain", dependencies=[Depends(require_dashboard_access)])
def option_chain_research(underlying: str = Query(default="SPY", min_length=1, max_length=10),
                          feed: str = Query(default="indicative", pattern="^(indicative|opra)$"),
                          db: Session = Depends(get_db)):
    """Probe option data entitlement and liquidity using no execution APIs."""
    try:
        adapter, _ = alpaca_connection.load_read_only_adapter(
            db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False
        )
        return assess_option_chain(adapter.get_option_chain(underlying, feed=feed),
                                   underlying=underlying.upper(), feed=feed)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"option research unavailable: {type(exc).__name__}")


@app.get("/research/market-scan", dependencies=[Depends(require_dashboard_access)])
def latest_market_scan(db: Session = Depends(get_db)):
    event = (db.query(models.AuditLogEntry)
             .filter(models.AuditLogEntry.event_type == "market_research_scan_recorded")
             .order_by(models.AuditLogEntry.timestamp.desc()).first())
    return {"scan": event.payload if event else None}


@app.post("/research/market-scan", dependencies=[Depends(require_dashboard_access)])
def run_market_scan(db: Session = Depends(get_db)):
    """Operator-triggered, strictly read-only data scan."""
    adapter, paper = alpaca_connection.load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    if not paper:
        raise HTTPException(status_code=409, detail="research scanner requires paper/read-only data credential")
    return {"scan": {"ranked": run_market_research_scan(db, adapter)}}


@app.get("/research/equity-scan", dependencies=[Depends(require_dashboard_access)])
def latest_equity_scan(db: Session = Depends(get_db)):
    event = (db.query(models.AuditLogEntry)
             .filter(models.AuditLogEntry.event_type == "equity_research_scan_recorded")
             .order_by(models.AuditLogEntry.timestamp.desc()).first())
    return {"scan": event.payload if event else None}


@app.post("/research/equity-scan", dependencies=[Depends(require_dashboard_access)])
def run_equity_scan(db: Session = Depends(get_db)):
    """Read-only liquid U.S. equity scan; it has no execution route."""
    adapter, paper = alpaca_connection.load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    if not paper:
        raise HTTPException(status_code=409, detail="research scanner requires paper/read-only data credential")
    return {"scan": {"ranked": run_equity_research_scan(db, adapter)}}


@app.get("/research/expanded-equity-scan", dependencies=[Depends(require_dashboard_access)])
def latest_expanded_equity_scan(db: Session = Depends(get_db)):
    event = (db.query(models.AuditLogEntry)
             .filter(models.AuditLogEntry.event_type == "expanded_equity_research_scan_recorded")
             .order_by(models.AuditLogEntry.timestamp.desc()).first())
    return {"scan": event.payload if event else None}


@app.post("/research/expanded-equity-scan", dependencies=[Depends(require_dashboard_access)])
def run_expanded_scan(db: Session = Depends(get_db)):
    """Run a bounded, read-only expanded equity scan; it cannot place an order."""
    adapter, paper = alpaca_connection.load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    if not paper:
        raise HTTPException(status_code=409, detail="research scanner requires paper/read-only data credential")
    return {"scan": {"ranked": run_expanded_equity_scan(db, adapter)}}


@app.get("/paper/status", dependencies=[Depends(require_dashboard_access)])
def get_paper_status(db: Session = Depends(get_db)):
    return paper_status(db)


@app.get("/paper/performance", dependencies=[Depends(require_dashboard_access)])
def get_paper_performance(db: Session = Depends(get_db)):
    return account_performance(db)


@app.get("/paper/activity", dependencies=[Depends(require_dashboard_access)])
def get_paper_activity(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    """Recent append-only paper-runtime actions for the operator dashboard."""
    events = (db.query(models.AuditLogEntry)
              .filter(models.AuditLogEntry.event_type.in_([
                  "paper_event_committed", "paper_trade_closed", "state_change",
                  "kill_switch", "risk_veto", "error", "alpaca_paper_monitor_cycle",
                  "reconciliation_resolved", "uncertain_broker_outcome", "order_submitted", "risk_decision", "alpaca_paper_worker_cycle_started", "alpaca_paper_worker_entries_blocked", "alpaca_paper_worker_cycle_completed",
              ]))
              .order_by(models.AuditLogEntry.timestamp.desc(), models.AuditLogEntry.id.desc())
              .limit(limit).all())
    return {"mode": "paper", "simulated": True, "events": [
        {"id": event.id, "timestamp": event.timestamp, "type": event.event_type,
         "actor": event.actor, "payload": event.payload}
        for event in events
    ]}


@app.get("/paper/insights", dependencies=[Depends(require_dashboard_access)])
def get_paper_insights(db: Session = Depends(get_db)):
    """Historical paper-only observations for the operations dashboard.

    Values are realized or recorded simulation data. The endpoint deliberately
    provides no forecasts, recommendations, or live-market claims.
    """
    snapshots = list(reversed(db.query(models.AccountSnapshot)
                              .order_by(models.AccountSnapshot.timestamp.desc())
                              .limit(500).all()))
    high_water = 0.0
    curve = []
    for row in snapshots:
        high_water = max(high_water, row.equity or 0.0)
        drawdown = 0.0 if high_water <= 0 else max(0.0, 1 - row.equity / high_water)
        curve.append({"timestamp": row.timestamp, "equity": row.equity,
                      "cash": row.cash, "drawdown": drawdown})

    closed = (db.query(models.TradeDecisionRecord)
              .filter(models.TradeDecisionRecord.status == "closed")
              .order_by(models.TradeDecisionRecord.timestamp.desc()).limit(200).all())
    trades = [{"timestamp": row.timestamp, "symbol": row.symbol,
               "strategy": row.strategy, "pnl": row.pnl, "r_multiple": row.r_multiple,
               "exit_reason": row.exit_reason} for row in reversed(closed)]
    strategy = {}
    for row in trades:
        bucket = strategy.setdefault(row["strategy"] or "unclassified",
                                     {"strategy": row["strategy"] or "unclassified", "trades": 0,
                                      "wins": 0, "pnl": 0.0, "r_total": 0.0})
        bucket["trades"] += 1
        bucket["wins"] += int((row["pnl"] or 0) > 0)
        bucket["pnl"] += row["pnl"] or 0.0
        bucket["r_total"] += row["r_multiple"] or 0.0
    strategy_rows = []
    for row in strategy.values():
        row["win_rate"] = row["wins"] / row["trades"] if row["trades"] else None
        strategy_rows.append(row)

    vetoes = (db.query(models.AuditLogEntry)
              .filter(models.AuditLogEntry.event_type.in_(["risk_veto", "kill_switch", "error"]))
              .order_by(models.AuditLogEntry.timestamp.desc()).limit(50).all())
    validations = (db.query(models.StrategyValidationRecord)
                   .order_by(models.StrategyValidationRecord.evaluated_at.desc()).all())
    return {"mode": "paper", "simulated": True, "equity_curve": curve,
            "closed_trades": trades, "strategy_breakdown": strategy_rows,
            "strategy_validations": [{"strategy": row.strategy,
                                      "methodology_version": row.methodology_version,
                                      "evaluated_at": row.evaluated_at,
                                      "trades": row.trades, "win_rate": row.win_rate,
                                      "total_return": row.total_return,
                                      "max_drawdown": row.max_drawdown,
                                      "passed": row.passed, "reasons": row.reasons}
                                     for row in validations],
            "risk_events": [{"timestamp": item.timestamp, "type": item.event_type,
                             "payload": item.payload} for item in vetoes]}


class AlpacaConnectRequest(BaseModel):
    api_key: str
    api_secret: str
    paper: bool = True


@app.get("/brokers/alpaca/status", dependencies=[Depends(require_dashboard_access)])
def alpaca_status(db: Session = Depends(get_db)):
    return alpaca_connection.status(db)


@app.post("/brokers/alpaca/connect", dependencies=[Depends(require_dashboard_access)])
def alpaca_connect(payload: AlpacaConnectRequest, db: Session = Depends(get_db)):
    try:
        return alpaca_connection.connect(db, payload.api_key, payload.api_secret,
                                         settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=payload.paper)
    except (BrokerOAuthConfigurationError, AlpacaBrokerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/brokers/alpaca/readiness", dependencies=[Depends(require_dashboard_access)])
def alpaca_readiness(db: Session = Depends(get_db)):
    try:
        return alpaca_connection.verify_read_only(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    except (BrokerOAuthConfigurationError, AlpacaBrokerError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/brokers/etrade/status", dependencies=[Depends(require_dashboard_access)])
def etrade_status(db: Session = Depends(get_db)):
    return etrade_connection.status(db)


@app.get("/brokers/etrade/connect", response_class=HTMLResponse,
         dependencies=[Depends(require_dashboard_access)])
def etrade_connect(db: Session = Depends(get_db)):
    """Show a one-time broker authorization link and verifier form."""
    if not etrade_connection.status(db)["api_key_configured"]:
        return HTMLResponse('<h1>E*TRADE API key needed</h1><p>Complete the '
            '<a href="https://developer.etrade.com/getting-started">E*TRADE Individual live API key application</a> '
            'and configure the key and secret securely on the server. Do not paste credentials into the dashboard.</p>',
            status_code=503, headers={"Cache-Control": "no-store"})
    try:
        url, token = etrade_connection.begin(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    except ETradeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    page = ('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Connect E*TRADE</title><style>body{font:18px system-ui;background:#101820;color:#fff;'
            'max-width:620px;margin:48px auto;padding:18px}a,button{color:#fff;background:#146b5b;'
            'padding:12px;border:0;border-radius:8px}input{font:inherit;padding:12px;width:100%;'
            'box-sizing:border-box;margin:16px 0}</style></head><body><h1>Connect E*TRADE</h1>'
            '<p>Open E*TRADE in a new tab, approve access, then enter its one-time verification code here.</p>'
            '<p><a target="_blank" rel="noopener noreferrer" href="' + html.escape(url, quote=True) + '">Open E*TRADE authorization</a></p>'
            '<form id="verify"><label>Verification code<input id="code" required autocomplete="off"></label>'
            '<button>Finish read-only connection</button></form><p id="result" role="status"></p>'
            '<script>document.getElementById("verify").onsubmit=async e=>{e.preventDefault();'
            'const r=await fetch("/brokers/etrade/complete",{method:"POST",headers:{"Content-Type":"application/json"},'
            'body:JSON.stringify({request_token:' + json.dumps(token).replace("<", "\\u003c") + ',verifier:document.getElementById("code").value.trim()})});'
            'document.getElementById("result").textContent=r.ok?"Connected read-only. You may return to the dashboard.":'
            '"Connection failed or expired. Open a new connection page and retry.";};</script></body></html>')
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


class ETradeVerifier(BaseModel):
    request_token: str
    verifier: str


@app.post("/brokers/etrade/complete", dependencies=[Depends(require_dashboard_access)])
def etrade_complete(body: ETradeVerifier, db: Session = Depends(get_db)):
    try:
        return etrade_connection.finish(db, settings.BROKER_TOKEN_ENCRYPTION_KEY,
                                        body.request_token, body.verifier)
    except ETradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/brokers/etrade/accounts", dependencies=[Depends(require_dashboard_access)])
def etrade_accounts(db: Session = Depends(get_db)):
    try:
        adapter = etrade_connection.reader(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
        return {"broker": "etrade_personal", "accounts": [
            {"last4": a["account_last4"], "status": a["status"],
             "type": a["account_type"],
             "balance": adapter.account_balance(a["account_id_key"])}
            for a in adapter.list_accounts() if a["institution_type"] == "BROKERAGE"],
            "execution_enabled": False}
    except ETradeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/brokers/etrade/options/chain", dependencies=[Depends(require_dashboard_access)])
def etrade_option_chain(symbol: str = Query(min_length=1, max_length=10),
                        year: int = Query(ge=2020, le=2100),
                        month: int = Query(ge=1, le=12),
                        day: int = Query(ge=1, le=31),
                        db: Session = Depends(get_db)):
    """Inspect account-authorized option quotes without inferring trading readiness."""
    try:
        adapter = etrade_connection.reader(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
        chain = adapter.option_chain(symbol, expiry_year=year, expiry_month=month,
                                     expiry_day=day)
        return {**chain, "execution_enabled": False}
    except ETradeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/brokers/robinhood/status", dependencies=[Depends(require_dashboard_access)])
def robinhood_status(db: Session = Depends(get_db)):
    """Connection state without exposing credentials or account data."""
    status = connection_status(db)
    return {
        **status,
        "setup_url": "https://robinhood.com/us/en/support/articles/agentic-trading-overview/",
        "account_requirement": "A dedicated Robinhood Agentic Trading account is required.",
    }


@app.get("/brokers/robinhood/connect", dependencies=[Depends(require_dashboard_access)])
def robinhood_connect(fresh: bool = False, db: Session = Depends(get_db)):
    """Begin the user-authorized OAuth flow. This endpoint never invokes MCP tools.

    ``?fresh=1`` registers a new OAuth client instead of reusing the saved one."""
    try:
        return RedirectResponse(start_connection(db, settings.BROKER_OAUTH_REDIRECT_URL,
                                                 force_new_client=fresh), status_code=302)
    except BrokerOAuthConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/brokers/robinhood/connect-manual", response_class=HTMLResponse,
         dependencies=[Depends(require_dashboard_access)])
def robinhood_connect_manual(db: Session = Depends(get_db)):
    """Loopback OAuth: approve at Robinhood, then paste the final address back here."""
    from app.brokers.robinhood_oauth import LOOPBACK_REDIRECT_URL
    try:
        url = start_connection(db, LOOPBACK_REDIRECT_URL)
    except BrokerOAuthConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    page = ('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Connect Robinhood</title><style>body{font:17px system-ui;background:#0b0e11;color:#eaecef;'
            'max-width:640px;margin:40px auto;padding:18px;line-height:1.5}a.btn,button{display:inline-block;'
            'color:#0b0e11;background:#f0b90b;padding:12px 16px;border:0;border-radius:8px;font-weight:700;'
            'text-decoration:none;cursor:pointer}textarea{font:14px monospace;width:100%;box-sizing:border-box;'
            'height:110px;margin:12px 0;padding:10px;background:#12161b;color:#eaecef;border:1px solid #2b3139;'
            'border-radius:8px}ol li{margin:8px 0}</style></head><body><h1>Connect Robinhood</h1><ol>'
            '<li><a class="btn" target="_blank" rel="noopener noreferrer" href="' + html.escape(url, quote=True) +
            '">Open Robinhood approval</a></li><li>Sign in and approve. Your browser will then show a '
            '<b>&ldquo;can&rsquo;t connect&rdquo; / &ldquo;site can&rsquo;t be reached&rdquo;</b> page &mdash; that is expected.</li>'
            '<li>Copy the <b>full address</b> from that page&rsquo;s address bar (it starts with '
            '<code>http://127.0.0.1:8765/oauth/callback?code=</code>) and paste it below within 10 minutes.</li></ol>'
            '<form id="f"><textarea id="u" placeholder="http://127.0.0.1:8765/oauth/callback?code=...&amp;state=..." required></textarea>'
            '<button>Finish connection</button></form><p id="r" role="status"></p>'
            '<script>document.getElementById("f").onsubmit=async e=>{e.preventDefault();const r=await fetch('
            '"/brokers/robinhood/complete-manual",{method:"POST",headers:{"Content-Type":"application/json"},'
            'body:JSON.stringify({url:document.getElementById("u").value.trim()})});const d=await r.json().catch(()=>({}));'
            'document.getElementById("r").textContent=r.ok?"Connected. Return to the dashboard and reload it.":'
            '"Failed: "+(d.detail||r.status)+". Open this page again and retry.";};</script></body></html>')
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


class RobinhoodManualCallback(BaseModel):
    url: str


@app.post("/brokers/robinhood/complete-manual", dependencies=[Depends(require_dashboard_access)])
def robinhood_complete_manual(body: RobinhoodManualCallback, db: Session = Depends(get_db)):
    from urllib.parse import parse_qs, urlparse
    from app.brokers.robinhood_oauth import LOOPBACK_REDIRECT_URL
    parsed = urlparse(body.url.strip())
    params = parse_qs(parsed.query)
    if parsed.scheme + "://" + parsed.netloc + parsed.path != LOOPBACK_REDIRECT_URL:
        raise HTTPException(status_code=400, detail="That is not the Robinhood callback address")
    if "error" in params:
        raise HTTPException(status_code=400, detail="Robinhood returned: " + params["error"][0])
    code, state = (params.get("code") or [""])[0], (params.get("state") or [""])[0]
    if not code or not state:
        raise HTTPException(status_code=400, detail="The address is missing code or state")
    try:
        return finish_connection(db, state, code, LOOPBACK_REDIRECT_URL, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    except BrokerOAuthConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Robinhood rejected the code ({type(exc).__name__})")


@app.get("/brokers/robinhood/callback")
def robinhood_callback(state: str, code: str, db: Session = Depends(get_db)):
    try:
        result = finish_connection(db, state, code, settings.BROKER_OAUTH_REDIRECT_URL,
                                   settings.BROKER_TOKEN_ENCRYPTION_KEY)
        return JSONResponse(result)
    except BrokerOAuthConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/brokers/robinhood/capabilities", dependencies=[Depends(require_dashboard_access)])
def robinhood_capabilities(db: Session = Depends(get_db)):
    """Discover broker-advertised tools only; this endpoint cannot call one."""
    try:
        return discover_capabilities(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    except (BrokerOAuthConfigurationError, RobinhoodMcpError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/brokers/robinhood/readiness", dependencies=[Depends(require_dashboard_access)])
def robinhood_readiness(db: Session = Depends(get_db)):
    """Verify broker data paths only; this endpoint never sends an order."""
    try:
        report = verify_agentic_readiness(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
        if report.get("read_only_ready"):
            log_and_commit(db, "broker_read_only_verified", {
                "broker": "robinhood_agentic_trading",
                "account_last4": str(report["expected_account_id"])[-4:],
                "open_positions": report["open_positions"],
                "open_orders": report["open_orders"],
                "execution_enabled": False,
            })
        return report
    except (BrokerOAuthConfigurationError, RobinhoodMcpError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


_robinhood_market_cache: dict[str, object] = {"expires_at": 0.0, "payload": None}


@app.get("/brokers/robinhood/market-access", dependencies=[Depends(require_dashboard_access)])
def robinhood_market_access(db: Session = Depends(get_db)):
    """Read-only ETF and crypto evidence for the dedicated Agentic account."""
    if time.monotonic() < _robinhood_market_cache["expires_at"] and _robinhood_market_cache["payload"] is not None:
        # Quote quality expires even when the broker-status response is cached.
        payload = copy.deepcopy(_robinhood_market_cache["payload"])
        for quote in payload["crypto"]["quotes"]:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(quote["as_of"].replace("Z", "+00:00"))).total_seconds()
                quote["age_seconds"] = max(0, age)
                quote["valid_for_execution"] = bool(quote["valid_for_execution"] and 0 <= age <= 5)
                if age > 5 and quote.get("quality_reason") == "current":
                    quote["quality_reason"] = "stale_quote"
            except (KeyError, TypeError, ValueError):
                quote["valid_for_execution"] = False
                quote["quality_reason"] = "invalid_timestamp"
        return payload
    try:
        adapter, account = load_agentic_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
        portfolio = adapter._portfolio()
        etfs = adapter.get_equity_tradability(["SPY", "QQQ", "IWM", "GLD", "TLT"])
        linked_crypto = bool(account.get("rhc_account_number"))
        crypto = {"linked_account": linked_crypto, "buying_power": None, "quotes": [],
                  "open_positions": None, "open_orders": None, "data_error": None,
                  "execution_enabled": False}
        if linked_crypto:
            try:
                crypto["buying_power"] = float(portfolio["crypto_buying_power"]["buying_power"])
                crypto["quotes"] = adapter.get_crypto_quotes(["BTC-USD", "ETH-USD"])
                crypto["open_positions"] = len(adapter.get_crypto_positions())
                crypto["open_orders"] = len(adapter.get_crypto_orders())
            except (RobinhoodMcpError, KeyError, TypeError, ValueError) as exc:
                crypto["data_error"] = type(exc).__name__
        option_level = account.get("user_option_level") or account.get("option_level") or "option_level_0"
        payload = {"broker": "robinhood_agentic_trading", "account_last4": str(account["account_id"])[-4:],
                   "options": {"approved_level": option_level,
                               "long_options_approved": option_level in {"option_level_2", "option_level_3"},
                               "spreads_approved": option_level == "option_level_3",
                               "execution_enabled": False},
                   "etfs": [{"symbol": row.get("symbol"), "tradable": row.get("tradeable") is True
                             and row.get("state") == "active",
                             "fractional": row.get("fractional_tradability") == "tradable"}
                            for row in etfs], "crypto": crypto, "execution_enabled": False,
                   "as_of": datetime.now(timezone.utc).isoformat()}
        # Execution-quality crypto quotes expire after five seconds. A longer
        # cache made a fresh broker quote look stale on a quick page reload.
        _robinhood_market_cache.update(expires_at=time.monotonic() + 4, payload=payload)
        return payload
    except (BrokerOAuthConfigurationError, RobinhoodMcpError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/brokers/robinhood/options/quote", dependencies=[Depends(require_dashboard_access)])
def robinhood_option_quote(symbol: str = Query(min_length=1, max_length=6),
                           expiration: str = Query(min_length=10, max_length=10),
                           strike: str = Query(min_length=1, max_length=20),
                           option_type: str = Query(pattern="^(call|put)$"),
                           db: Session = Depends(get_db)):
    """User-triggered read-only option quote; never routes an order."""
    try:
        adapter, account = load_agentic_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
        chains = [chain for chain in adapter.get_option_chains(symbol.upper())
                  if expiration in (chain.get("expiration_dates") or [])]
        contracts = [contract for chain in chains
                     for contract in adapter.get_option_instruments(chain["id"], expiration,
                                                                    strike, option_type)
                     if contract.get("state") == "active"
                     and contract.get("tradability") == "tradable"]
        if not contracts:
            return {"symbol": symbol.upper(), "contracts": [], "execution_enabled": False,
                    "reason": "No active tradable contract matched the filter"}
        if len(contracts) > 20:
            raise RobinhoodMcpError("Too many matching option contracts; narrow the filter")
        return {"symbol": symbol.upper(), "account_last4": str(account["account_id"])[-4:],
                "approved_level": account.get("user_option_level") or account.get("option_level") or "option_level_0",
                "contracts": adapter.get_option_quotes(contracts), "execution_enabled": False}
    except (BrokerOAuthConfigurationError, RobinhoodMcpError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    if not dashboard_access_granted(request):
        return RedirectResponse("/login", status_code=303)
    # The operator console is a live view.  Never let an intermediary or the
    # browser retain an earlier dashboard shell after a deployment.
    return HTMLResponse(DASHBOARD_HTML, headers={"Cache-Control": "no-store, max-age=0"})


class DashboardLogin(BaseModel):
    username: str
    password: str


LOGIN_HTML = """<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Veloikos Trading</title><style>body{margin:0;background:#070d0b;color:#f4f0e6;font:16px system-ui;display:grid;place-items:center;height:100vh}.card{width:320px;padding:32px;background:#0d1713;border:1px solid #2a4939;border-radius:14px}input,button{box-sizing:border-box;width:100%;padding:12px;margin:8px 0;border-radius:8px;border:1px solid #496852;background:#09120e;color:#f4f0e6}button{background:#c9a45c;border:0;font-weight:700;cursor:pointer}.error{color:#ff8b8b;min-height:20px}</style></head><body><main class=card><img src="/static/veloikos-mark.png" alt="Veloikos Trading" style="width:70px;height:70px;object-fit:contain"><h1>Veloikos Trading</h1><p>Sign in to the live trading console.</p><input id=u autocomplete=username placeholder=Username><input id=p type=password autocomplete=current-password placeholder=Password><div id=e class=error></div><button id=b>Sign in</button></main><script>document.querySelector('#b').onclick=async()=>{const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u.value,password:p.value})});if(r.ok)location='/dashboard';else e.textContent='Incorrect username or password';};</script></body></html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(LOGIN_HTML)


@app.post("/login")
def login(payload: DashboardLogin):
    token = issue_dashboard_session(payload.username, payload.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    response = JSONResponse({"authenticated": True})
    response.set_cookie("project100_dashboard", token, httponly=True, secure=True,
                        samesite="strict", max_age=60 * 60 * 12, path="/")
    return response

@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    status = paper_status(db)
    return JSONResponse(status, status_code=200 if status["ready"] else 503)


@app.get("/health")
def health():
    return {"status": "ok", "trading_mode": settings.TRADING_MODE, "autonomy_level": settings.AUTONOMY_LEVEL}


@app.get("/scanner/signals", dependencies=[Depends(require_dashboard_access)])
def scanner_signals(db: Session = Depends(get_db)):
    """Watch-only multi-market scanner: recent signals and forward scoreboard."""
    from app.research.multi_market_rules import RULES, RULES_VERSION
    rows = (db.query(models.ScannerSignal)
            .order_by(models.ScannerSignal.signal_date.desc(), models.ScannerSignal.momentum_6m.desc())
            .limit(400).all())
    item = lambda r: {"symbol": r.symbol, "rule": r.rule, "group": r.asset_group,
                      "signal_date": r.signal_date, "signal_close": r.signal_close,
                      "stop_pct": r.stop_pct, "target_pct": r.target_pct, "status": r.status,
                      "mark_pct": r.mark_pct, "result_pct": r.result_pct, "exit_reason": r.exit_reason,
                      "momentum_6m": r.momentum_6m}
    board: dict[tuple, list] = {}
    for r in db.query(models.ScannerSignal).filter(models.ScannerSignal.status == "closed").all():
        board.setdefault((r.rule, r.asset_group), []).append(r.result_pct or 0.0)
    score = [{"rule": k[0], "group": k[1], "closed": len(v), "win_rate": sum(x > 0 for x in v) / len(v),
              "avg_result": sum(v) / len(v)} for k, v in board.items()]
    score.sort(key=lambda x: (-x["avg_result"], -x["closed"]))
    return {"rules_version": RULES_VERSION, "order_submission": False,
            "rules": {k: {"stop": r.stop, "target": r.target, "max_hold_days": r.max_hold,
                          "description": r.description} for k, r in RULES.items()},
            "signals": [item(r) for r in rows], "scoreboard": score}


@app.get("/system/state", dependencies=[Depends(require_dashboard_access)])
def get_state(db: Session = Depends(get_db)):
    rec = StateManager(db, settings).get_record()
    return {"scope": rec.id, "state": rec.state, "reason": rec.reason, "updated_at": rec.updated_at}


@app.get("/config/risk", dependencies=[Depends(require_dashboard_access)])
def get_risk_config():
    """Read-only view of active risk configuration (no secrets)."""
    return {
        "MAX_RISK_PER_TRADE": settings.MAX_RISK_PER_TRADE,
        "MAX_DAILY_LOSS": settings.MAX_DAILY_LOSS,
        "MAX_WEEKLY_DRAWDOWN": settings.MAX_WEEKLY_DRAWDOWN,
        "MAX_TOTAL_DRAWDOWN": settings.MAX_TOTAL_DRAWDOWN,
        "MAX_POSITIONS": settings.MAX_POSITIONS,
        "ALLOW_MARGIN": settings.ALLOW_MARGIN,
        "ALLOW_OPTIONS": settings.ALLOW_OPTIONS,
        "ALLOW_SHORTS": settings.ALLOW_SHORTS,
        "ALLOW_LEVERAGE": settings.ALLOW_LEVERAGE,
        "AUTO_EXECUTION": settings.AUTO_EXECUTION,
    }


@app.get("/live/readiness", dependencies=[Depends(require_dashboard_access)])
def live_readiness(db: Session = Depends(get_db)):
    try:
        # Live credentials are stored separately and are read-only here.  This
        # endpoint is a visibility gate, never an activation path.
        broker = alpaca_connection.verify_read_only(db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
        log_and_commit(db, "alpaca_live_read_only_verified", {
            "read_only_ready": bool(broker.get("read_only_ready")),
            "paper": bool(broker.get("paper")),
            "verified_at": broker.get("verified_at"),
        })
    except Exception:
        broker = {"read_only_ready": False, "paper": False}
    # Only a recorded external-paper lifecycle counts here; a unit test or a
    # favorable dashboard state cannot promote live execution.
    evidence = (db.query(models.AuditLogEntry)
                .filter(models.AuditLogEntry.event_type == "alpaca_paper_lifecycle_passed")
                .order_by(models.AuditLogEntry.timestamp.desc()).first())
    report = live_readiness_report(
        settings, broker, market_open=False,
        external_paper_lifecycle_verified=evidence is not None,
        current_state=(db.get(models.SystemStateRecord, settings.ALPACA_LIVE_STATE_SCOPE).state
                       if db.get(models.SystemStateRecord, settings.ALPACA_LIVE_STATE_SCOPE) else None),
    )
    report["external_paper_lifecycle_evidence"] = evidence.payload if evidence else None
    return report


@app.get("/paper/execution-worker", dependencies=[Depends(require_dashboard_access)])
def paper_execution_worker(db: Session = Depends(get_db)):
    row = db.get(models.ExternalPaperRuntimeState, "alpaca-paper-1")
    if not row:
        return {"configured": True, "started": False, "status": "waiting"}
    return {"configured": True, "started": True, "status": row.status, "heartbeat": row.heartbeat, "references": row.payload.get("references", {})}


@app.get("/brokers/alpaca/paper-portfolio", dependencies=[Depends(require_dashboard_access)])
def alpaca_paper_portfolio(db: Session = Depends(get_db)):
    try:
        adapter, paper = alpaca_connection.load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
        if not paper:
            raise HTTPException(status_code=409, detail="stored Alpaca credential is not paper")
        from app.services.protective_order_verification import verify_protective_orders
        positions, orders = adapter.get_positions(), adapter.get_orders()
        protection = verify_protective_orders(adapter)
        active_statuses = {"new", "accepted", "pending", "open", "partially_filled"}
        active_orders = [order for order in orders if str(order.get("status")) in active_statuses]
        historical_orders = [order for order in orders if str(order.get("status")) not in active_statuses]
        return {"paper_only": True, "positions": positions, "active_orders": active_orders,
                "historical_orders": historical_orders, "protection": protection}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"paper portfolio unavailable: {type(exc).__name__}")


@app.get("/brokers/alpaca/live-portfolio", dependencies=[Depends(require_dashboard_access)])
def alpaca_live_portfolio(db: Session = Depends(get_db)):
    """Read-only live-account snapshot for the operator dashboard."""
    try:
        now = time.monotonic()
        cached = _live_portfolio_cache.get("payload")
        if cached is not None and now < float(_live_portfolio_cache["expires_at"]):
            return cached
        adapter, paper = alpaca_connection.load_read_only_adapter(
            db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False
        )
        if paper:
            raise HTTPException(status_code=409, detail="stored credential is not live")
        positions, orders = adapter.get_positions(), adapter.get_orders()
        active_statuses = {"new", "accepted", "pending", "open", "partially_filled", "held"}
        # nested=true puts bracket stop/target legs under a filled parent; list them too.
        flat = list(orders) + [leg for order in orders for leg in (order.get("legs") or [])]
        active_orders = [order for order in flat if str(order.get("status")) in active_statuses]
        payload = {"live": True, "balances": adapter.get_balances(),
                   "positions": positions, "active_orders": active_orders,
                   "market_clock": adapter.get_market_clock()}
        _live_portfolio_cache.update({"payload": payload,
                                      "expires_at": now + _LIVE_PORTFOLIO_CACHE_SECONDS})
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"live portfolio unavailable: {type(exc).__name__}")


@app.get("/live/activity", dependencies=[Depends(require_dashboard_access)])
def live_activity(limit: int = Query(default=80, ge=1, le=200), db: Session = Depends(get_db)):
    """Recent live-worker audit events; contains no credentials or order authority."""
    events = (db.query(models.AuditLogEntry)
              .filter((models.AuditLogEntry.event_type.like("alpaca_live%")) |
                      (models.AuditLogEntry.event_type == "risk_decision"))
              .order_by(models.AuditLogEntry.timestamp.desc(), models.AuditLogEntry.id.desc())
              .limit(limit).all())
    return {"events": [{"id": event.id, "timestamp": event.timestamp,
                        "type": event.event_type, "actor": event.actor,
                        "payload": event.payload} for event in events]}


@app.get("/live/trades", dependencies=[Depends(require_dashboard_access)])
def live_trades(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    """Read-only live trade ledger for the operator terminal."""
    live_ids = _audited_live_trade_ids(db)
    if not live_ids:
        return {"trades": []}
    rows = (db.query(models.TradeDecisionRecord)
            .filter(models.TradeDecisionRecord.trade_id.in_(live_ids),
                    models.TradeDecisionRecord.order_id.isnot(None),
                    models.TradeDecisionRecord.strategy.in_((DailyTrendPullback.name,
                                                             BroadDailyTrendPullback.name,
                                                             STAGE_RUNNER_VERSION)))
            .order_by(models.TradeDecisionRecord.timestamp.desc())
            .limit(limit).all())
    return {"trades": [{
        "trade_id": row.trade_id, "timestamp": row.timestamp, "symbol": row.symbol,
        "strategy": row.strategy, "status": row.status, "quantity": row.position_size,
        "entry_price": row.fill_price or row.entry_price, "stop_price": row.stop_price,
        "target_price": row.target_price, "exit_price": row.exit_price,
        "exit_reason": row.exit_reason, "pnl": row.pnl,
    } for row in rows]}


@app.get("/allocator/lots", dependencies=[Depends(require_dashboard_access)])
def allocator_lots(mode: str = Query(default="live", pattern="^(live|paper|binance|binance-paper)$"),
                   limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    """Read-only allocator positions with their stop/target (broker bracket or worker-watched)."""
    rows = (db.query(models.AllocatorLot).filter(models.AllocatorLot.mode == mode)
            .order_by(models.AllocatorLot.status.desc(), models.AllocatorLot.opened_on.desc())
            .limit(limit).all())
    out = []
    for r in rows:
        pnl = (round((r.exit_price - r.entry_price) * r.quantity, 2)
               if r.status == "closed" and r.exit_price is not None and r.quantity else None)
        out.append({"id": r.id, "symbol": r.symbol, "sleeve": r.sleeve, "rule": r.rule,
                    "quantity": r.quantity, "entry_price": r.entry_price, "stop_price": r.stop_price,
                    "target_price": r.target_price, "max_hold_days": r.max_hold_days,
                    "broker_bracket": bool(r.broker_bracket), "confirmed": bool(r.confirmed),
                    "status": r.status, "opened_on": r.opened_on, "closed_on": r.closed_on,
                    "exit_reason": r.exit_reason, "exit_price": r.exit_price, "pnl": pnl})
    return {"mode": mode, "lots": out}


def _audited_live_trade_ids(db: Session) -> set[str]:
    """Use the live worker audit trail to avoid presenting paper fills as live."""
    events = (db.query(models.AuditLogEntry)
              .filter(models.AuditLogEntry.event_type.in_((
                  "alpaca_live_worker_cycle_completed", "alpaca_live_trade_closed"))).all())
    return {str(event.payload["trade_id"]) for event in events
            if isinstance(event.payload, dict) and event.payload.get("trade_id")}


@app.get("/live/decision-context", dependencies=[Depends(require_dashboard_access)])
def live_decision_context(db: Session = Depends(get_db)):
    """Recorded live decisions and validation evidence, with no broker calls."""
    live_ids = _audited_live_trade_ids(db)
    trade = (db.query(models.TradeDecisionRecord)
             .filter(models.TradeDecisionRecord.trade_id.in_(live_ids))
             .order_by(models.TradeDecisionRecord.timestamp.desc()).first()) if live_ids else None
    validation = db.get(models.StrategyValidationRecord, BroadDailyTrendPullback.name)
    intraday = db.get(models.StrategyValidationRecord, INTRADAY_RESEARCH_VERSION)
    state = db.get(models.SystemStateRecord, settings.ALPACA_LIVE_STATE_SCOPE)
    last_scan = (db.query(models.AuditLogEntry)
                 .filter(models.AuditLogEntry.event_type.in_((
                     "alpaca_live_worker_cycle_completed", "alpaca_live_worker_no_qualifying_signal",
                     "alpaca_broad_live_worker_rate_limited")))
                 .order_by(models.AuditLogEntry.timestamp.desc()).first())
    def evidence(row):
        return None if row is None else {"passed": row.passed, "trades": row.trades,
            "win_rate": row.win_rate, "total_return": row.total_return,
            "max_drawdown": row.max_drawdown, "evaluated_at": row.evaluated_at,
            "sample_start": row.sample_start, "sample_end": row.sample_end,
            "methodology_version": row.methodology_version, "reasons": row.reasons}
    return {
        "state": {"value": state.state, "reason": state.reason} if state else None,
        "live_strategy": {"version": BroadDailyTrendPullback.name,
            "universe": list(BroadDailyTrendPullback.universe),
            "entry_rules": {"above_50_day_average": True, "five_day_pullback_at_least_pct": 1.5,
                            "maximum_quote_age_seconds": 15, "maximum_spread_pct": 1.0},
            "initial_stop_pct": STOP_LOSS * 100, "target_pct": TAKE_PROFIT * 100,
            "maximum_open_positions_in_worker": 1,
            "decision_frequency": "at most one submitted decision per symbol per day"},
        "live_validation": evidence(validation),
        "intraday_research": {"version": INTRADAY_RESEARCH_VERSION, "evidence": evidence(intraday),
                              "execution_enabled": False},
        "latest_trade": None if trade is None else {"trade_id": trade.trade_id,
            "timestamp": trade.timestamp, "symbol": trade.symbol, "strategy": trade.strategy,
            "status": trade.status, "entry_thesis": trade.entry_thesis,
            "technical_conditions": trade.technical_conditions,
            "risk_engine_result": trade.risk_engine_result,
            "quantity": trade.position_size, "entry_price": trade.fill_price or trade.entry_price,
            "stop_price": trade.stop_price, "target_price": trade.target_price,
            "risk_dollars": trade.risk_dollars, "exit_price": trade.exit_price,
            "exit_reason": trade.exit_reason, "pnl": trade.pnl},
        "last_worker_event": None if last_scan is None else {"type": last_scan.event_type,
            "timestamp": last_scan.timestamp, "payload": last_scan.payload},
        "capabilities": CapabilityRegistry().report(),
    }


@app.get("/live/milestones", dependencies=[Depends(require_dashboard_access)])
def live_milestones(db: Session = Depends(get_db)):
    from app.services.milestone_lifecycle import MilestonePolicy, read_stage
    policy = MilestonePolicy(first_target=settings.FIRST_MILESTONE,
                             starting_capital=settings.STARTING_CAPITAL)
    result = {"targets": policy.targets, "starting_capital": policy.starting_capital,
              "first_target": policy.first_target, "first_target_is_configured_default": True,
              "next_target": policy.first_target, "achieved": [], "phase": "account_unavailable",
              "broker_verified": False, "runtime_verified": False}
    try:
        reader, paper = alpaca_connection.load_read_only_adapter(
            db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
        accounts = reader.get_accounts()
        if paper or len(accounts) != 1 or not accounts[0].get('account_id'):
            return result
        stored = read_stage(db, 'live', str(accounts[0]['account_id']), policy)
        return {**result, **stored, "broker_verified": True,
                "recorded_observation_only": True}
    except Exception:
        return result


@app.get("/live/observer", dependencies=[Depends(require_dashboard_access)])
def live_observer(db: Session = Depends(get_db)):
    event=(db.query(models.AuditLogEntry)
           .filter(models.AuditLogEntry.event_type == 'live_account_observed')
           .order_by(models.AuditLogEntry.timestamp.desc()).first())
    if not event:
        return {'observed':False, 'healthy':False, 'order_execution_enabled':False}
    age=(datetime.now(timezone.utc)-event.timestamp.replace(tzinfo=timezone.utc)).total_seconds()
    return {**event.payload, 'observed':True, 'observed_at':event.timestamp,
            'age_seconds':age, 'healthy':0 <= age <= 180 and bool(event.payload.get('risk_ready'))}
