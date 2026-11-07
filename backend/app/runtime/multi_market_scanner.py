"""Watch-only multi-market scanner.

Once per US trading day (after the close) it pulls daily bars for ~140 US stocks
and ETFs from Alpaca's read-only data API and for BTC/ETH/SOL from Binance.US's
public market-data endpoint, records any new rule signals, and updates the
forward outcome of every open signal. It has no order path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
import uuid
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.models import ScannerSignal
from app.research.multi_market_rules import (
    CRYPTO, RULES_VERSION, US_UNIVERSE, evaluate, group_of, signals_on_last_bar,
)

ET = ZoneInfo("America/New_York")
BATCH = 15
BINANCE_KLINES = "https://api.binance.us/api/v3/klines"
CRYPTO_COST, US_COST = .002, .0005


def us_bars(adapter, symbols=US_UNIVERSE, days: int = 420, today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(ET).date()
    start = (today - dt.timedelta(days=days)).isoformat()
    end = today.isoformat()  # completed sessions only: bars strictly before today
    out: dict[str, list[dict]] = {}
    for k in range(0, len(symbols), BATCH):
        batch = list(symbols[k:k + BATCH])
        try:
            got = adapter.get_daily_bars_many(batch, start, end)
        except Exception:
            got = {}
        out.update({s: [b for b in rows if str(b["timestamp"])[:10] < end] for s, rows in got.items()})
        time.sleep(0.3)
    return out


def crypto_bars(client: httpx.Client | None = None, days: int = 420) -> dict:
    client = client or httpx.Client(timeout=15)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    out = {}
    for pair in CRYPTO:
        try:
            raw = client.get(BINANCE_KLINES, params={"symbol": pair.replace("/", ""), "interval": "1d",
                                                     "limit": days}).json()
            rows = [{"timestamp": dt.datetime.fromtimestamp(r[0] / 1000, dt.timezone.utc).date().isoformat(),
                     "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]),
                     "volume": float(r[5])} for r in raw]
            out[pair] = [r for r in rows if r["timestamp"] < today]  # drop the unfinished UTC day
        except Exception:
            continue
    return out


def signal_id(symbol, rule, date):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{RULES_VERSION}:{symbol}:{rule}:{date}"))


def record(db: Session, bars_by_symbol: dict, backfill_days: int = 0) -> dict:
    """Record new signals (optionally for each of the last ``backfill_days`` sessions) and
    update every open signal's outcome from the full bar history."""
    new = updated = 0
    for symbol, bars in bars_by_symbol.items():
        found = []
        for k in range(backfill_days, -1, -1):
            found += signals_on_last_bar(symbol, bars[:len(bars) - k] if k else bars)
        for s in found:
            sid = signal_id(symbol, s["rule"], s["signal_date"])
            if db.get(ScannerSignal, sid) is None:
                db.add(ScannerSignal(id=sid, rules_version=RULES_VERSION, symbol=symbol, rule=s["rule"],
                                     asset_group=s["group"], signal_date=s["signal_date"],
                                     signal_close=s["close"], stop_pct=s["stop_pct"],
                                     target_pct=s["target_pct"], max_hold=s["max_hold"],
                                     momentum_6m=s["momentum_6m"], status="waiting_entry"))
                new += 1
    db.flush()
    for sig in db.query(ScannerSignal).filter(ScannerSignal.status != "closed").all():
        bars = bars_by_symbol.get(sig.symbol)
        if not bars:
            continue
        out = evaluate(sig.rule, bars, sig.signal_date, CRYPTO_COST if "/" in sig.symbol else US_COST)
        sig.status = "closed" if out["status"] == "closed" else out["status"]
        sig.entry_price = out.get("entry", sig.entry_price)
        sig.mark_pct = out.get("mark_pct")
        sig.result_pct = out.get("result_pct")
        sig.exit_reason = out.get("exit_reason")
        sig.exit_date = out.get("exit_date")
        sig.updated_at = dt.datetime.utcnow()
        updated += 1
    db.commit()
    return {"new_signals": new, "signals_updated": updated, "order_submission": False}


def run_once(db: Session, adapter, client=None, backfill_days: int = 0) -> dict:
    bars = us_bars(adapter)
    bars.update(crypto_bars(client))
    result = record(db, bars, backfill_days)
    return {**result, "markets_with_data": sum(1 for v in bars.values() if v)}


def due(now: dt.datetime, last_run_day: str | None) -> bool:
    et = now.astimezone(ET)
    return et.weekday() < 5 and et.time() >= dt.time(16, 30) and last_run_day != et.date().isoformat()


def main() -> int:
    from app.brokers.alpaca_connection import load_read_only_adapter
    from app.core.config import Settings
    from app.db.session import initialize_schema

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--backfill-days", type=int, default=0,
                        help="also record signals from the last N sessions (first run only)")
    args = parser.parse_args()
    settings = Settings()
    engine = create_engine(args.database)
    initialize_schema(engine)
    last = None
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        if args.once or due(now, last):
            try:
                with Session(engine) as db:
                    adapter, _ = load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
                    print({"event": "scan", **run_once(db, adapter, backfill_days=args.backfill_days if last is None else 0)}, flush=True)
                last = now.astimezone(ET).date().isoformat()
            except Exception as exc:
                print({"event": "scan_failed", "error": type(exc).__name__, "order_submission": False}, flush=True)
        if args.once:
            return 0
        time.sleep(300)


if __name__ == "__main__":
    raise SystemExit(main())
