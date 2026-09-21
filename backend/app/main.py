import time

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import Base, engine, get_db, initialize_schema
from app.models import models  # noqa: F401 ensures models are registered
from app.core.config import settings
from app.runtime.paper import paper_status
from app.analytics.performance import account_performance
from app.brokers.robinhood_oauth import (BrokerOAuthConfigurationError, connection_status,
    finish_connection, start_connection)
from app.brokers.robinhood_mcp import RobinhoodMcpError, discover_capabilities
from app.brokers.robinhood_adapter import verify_agentic_readiness
from app.brokers import alpaca_connection
from app.security.dashboard import (require_dashboard_access, dashboard_access_granted,
                                    issue_dashboard_session)
from app.dashboard_html import DASHBOARD_HTML
from app.services.live_readiness import report as live_readiness_report
from app.audit.logger import log_and_commit

initialize_schema(engine)

app = FastAPI(title="Project 100", version="0.1.0-phase1")

# The browser refreshes its display every second, but Alpaca account endpoints
# must not be called at browser-poll frequency.  This short process-local cache
# keeps the display live while reserving API capacity for the execution worker.
_live_portfolio_cache: dict[str, object] = {"expires_at": 0.0, "payload": None}
_LIVE_PORTFOLIO_CACHE_SECONDS = 5.0


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
def robinhood_connect(db: Session = Depends(get_db)):
    """Begin the user-authorized OAuth flow. This endpoint never invokes MCP tools."""
    try:
        return RedirectResponse(start_connection(db, settings.BROKER_OAUTH_REDIRECT_URL), status_code=302)
    except BrokerOAuthConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


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
        return verify_agentic_readiness(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    except (BrokerOAuthConfigurationError, RobinhoodMcpError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    if not dashboard_access_granted(request):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(DASHBOARD_HTML)


class DashboardLogin(BaseModel):
    username: str
    password: str


LOGIN_HTML = """<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Project 100</title><style>body{margin:0;background:#08111f;color:#eaf2ff;font:16px system-ui;display:grid;place-items:center;height:100vh}.card{width:320px;padding:32px;background:#101d31;border:1px solid #29415f;border-radius:14px}input,button{box-sizing:border-box;width:100%;padding:12px;margin:8px 0;border-radius:8px;border:1px solid #405d80;background:#091728;color:#fff}button{background:#2b7fff;border:0;font-weight:700;cursor:pointer}.error{color:#ff8b8b;min-height:20px}</style></head><body><main class=card><h1>Project 100</h1><p>Sign in to the live dashboard.</p><input id=u autocomplete=username placeholder=Username><input id=p type=password autocomplete=current-password placeholder=Password><div id=e class=error></div><button id=b>Sign in</button></main><script>document.querySelector('#b').onclick=async()=>{const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u.value,password:p.value})});if(r.ok)location='/dashboard';else e.textContent='Incorrect username or password';};</script></body></html>"""


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


@app.get("/system/state", dependencies=[Depends(require_dashboard_access)])
def get_state(db: Session = Depends(get_db)):
    rec = db.get(models.SystemStateRecord, "current")
    if not rec:
        rec = models.SystemStateRecord(id="current", state="off", reason="initial")
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return {"state": rec.state, "reason": rec.reason, "updated_at": rec.updated_at}


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
        active_orders = [order for order in orders if str(order.get("status")) in active_statuses]
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
              .filter(models.AuditLogEntry.event_type.like("alpaca_live%"))
              .order_by(models.AuditLogEntry.timestamp.desc(), models.AuditLogEntry.id.desc())
              .limit(limit).all())
    return {"events": [{"id": event.id, "timestamp": event.timestamp,
                        "type": event.event_type, "actor": event.actor,
                        "payload": event.payload} for event in events]}
