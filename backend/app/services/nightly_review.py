"""Nightly review: what each trading account did in the last 24 hours, checked against
what the backtest says is normal. Read-only; runs inside the API after 20:05 ET and
pushes a one-line summary to subscribed phones.
"""
from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

from app.models.models import (AllocatorLot, AllocatorState, AppState, AuditLogEntry,
                               OwnerAcceptedExperiment)
from app.research.stress_gate import stress_result

ET = ZoneInfo("America/New_York")
ACCOUNTS = (  # mode, label, strategy, venue
    ("live", "Alpaca allocator (live)", "allocator-core-satellite-v1", "alpaca"),
    ("binance", "Binance.US crypto (live)", "binance-crypto-signals-v1", "binance"),
    ("paper", "Alpaca allocator (paper)", "allocator-core-satellite-v1", "alpaca"),
    ("binance-paper", "Binance.US crypto (paper)", "binance-crypto-signals-v1", "binance"),
)
TRADE_EVENTS = ("allocator_buy", "allocator_sell", "binance_buy", "binance_sell", "allocator_broker_exit")
FAIL_EVENTS = ("allocator_buy_failed", "allocator_sell_failed", "binance_buy_failed", "binance_sell_failed")


def _get(db, key):
    row = db.get(AppState, key)
    return json.loads(row.value) if row else None


def _put(db, key, value):
    row = db.get(AppState, key)
    text = json.dumps(value, default=str)
    if row is None:
        db.add(AppState(key=key, value=text))
    else:
        row.value = text
    db.commit()


def _events(db, since, types):
    rows = (db.query(AuditLogEntry).filter(AuditLogEntry.event_type.in_(types), AuditLogEntry.timestamp >= since)
            .order_by(AuditLogEntry.timestamp).all())
    return [(r.event_type, r.payload if isinstance(r.payload, dict) else {}, r.timestamp) for r in rows]


def review_account(db, mode, label, strategy, *, equity, now, prev_equity=None) -> dict | None:
    lots = db.query(AllocatorLot).filter_by(mode=mode).all()
    if not lots and equity is None:
        return None
    since = now.replace(tzinfo=None) - dt.timedelta(hours=24)
    trades = [{"event": t, "symbol": p.get("symbol"), "reason": p.get("reason"),
               "usd": p.get("notional", p.get("usd")), "price": p.get("price"), "at": str(ts)}
              for t, p, ts in _events(db, since, TRADE_EVENTS) if p.get("mode") == mode]
    failures = [p for t, p, _ in _events(db, since, FAIL_EVENTS) if p.get("mode") == mode]
    open_lots = [l for l in lots if l.status == "open"]
    days = {now.astimezone(ET).date().isoformat(), now.astimezone(dt.timezone.utc).date().isoformat(),
            (now.astimezone(ET).date() - dt.timedelta(days=1)).isoformat()}
    realized = round(sum((l.exit_price - l.entry_price) * l.quantity for l in lots
                         if l.status == "closed" and l.closed_on in days and l.exit_price is not None), 2)
    flags = []
    if failures:
        flags.append({"level": "warn", "text": f"{len(failures)} failed order(s): " +
                      ", ".join(sorted({str(f.get('symbol')) for f in failures}))})
    stale = [l.symbol for l in open_lots if not l.confirmed]
    if stale:
        flags.append({"level": "warn", "text": "Fill not confirmed yet: " + ", ".join(stale)})
    st = db.get(AllocatorState, mode)
    if st and st.halted:
        flags.append({"level": "alert", "text": f"Account halted: {st.reason}"})
    change = None
    if equity is not None and prev_equity:
        change = equity / prev_equity - 1
        bands = (stress_result(strategy) or {}).get("daily_return_bands") or {}
        if bands and change < bands.get("p01", -1):
            flags.append({"level": "alert", "text": f"Down {change:.1%} — worse than 99% of backtest days"})
        elif bands and change > bands.get("p99", 1):
            flags.append({"level": "info", "text": f"Up {change:.1%} — better than 99% of backtest days"})
    if equity is not None and st and st.peak_equity:
        dd = 1 - equity / st.peak_equity
        if dd >= 0.40:
            flags.append({"level": "alert", "text": f"{dd:.0%} below peak — circuit breaker stops new buys at 50%"})
        elif dd >= 0.25:
            flags.append({"level": "warn", "text": f"{dd:.0%} below peak"})
    weekday = now.astimezone(ET).weekday() < 5
    expected_day = (now.astimezone(dt.timezone.utc).date() if mode.startswith("binance")
                    else now.astimezone(ET).date()).isoformat()
    if st and (mode.startswith("binance") or weekday) and st.last_daily_review != expected_day:
        flags.append({"level": "warn", "text": "Worker did not run its daily check today — is it up?"})
    return {"mode": mode, "label": label, "strategy": strategy, "equity": equity,
            "change": round(change, 4) if change is not None else None, "realized_today": realized,
            "open_positions": [{"symbol": l.symbol, "qty": l.quantity, "entry": l.entry_price,
                                "stop": l.stop_price, "target": l.target_price} for l in open_lots],
            "trades": trades, "flags": flags}


def summary_line(acct: dict) -> str:
    eq = f"${acct['equity']:,.2f}" if acct.get("equity") is not None else "—"
    ch = f" ({acct['change']:+.1%})" if acct.get("change") is not None else ""
    n = len(acct["trades"])
    issues = len([f for f in acct["flags"] if f["level"] in ("warn", "alert")])
    return (f"{acct['label']}: {eq}{ch}, {n} trade{'s' if n != 1 else ''}, "
            f"{len(acct['open_positions'])} open, " + (f"{issues} issue{'s' if issues != 1 else ''}" if issues else "no issues"))


def build(db, equities: dict, now: dt.datetime | None = None, *, persist: bool = True) -> dict:
    """equities: {mode: current equity or None}. Stores and returns the report."""
    now = now or dt.datetime.now(dt.timezone.utc)
    day = now.astimezone(ET).date().isoformat()
    prev = _get(db, "nightly_equity") or {}
    accounts = []
    for mode, label, strategy, _ in ACCOUNTS:
        a = review_account(db, mode, label, strategy, equity=equities.get(mode), now=now, prev_equity=prev.get(mode))
        if a:
            accounts.append(a)
    approvals = {r.strategy: not r.revoked for r in db.query(OwnerAcceptedExperiment).all()}
    issues = sum(1 for a in accounts for f in a["flags"] if f["level"] in ("warn", "alert"))
    report = {"day": day, "generated_at": now.isoformat(), "accounts": accounts, "approvals": approvals,
              "issues": issues, "lines": [summary_line(a) for a in accounts]}
    if not persist:
        return report
    _put(db, f"nightly:{day}", report)
    _put(db, "nightly_latest", report)
    _put(db, "nightly_equity", {**prev, **{k: v for k, v in equities.items() if v is not None}})
    history = _get(db, "nightly_index") or []
    _put(db, "nightly_index", ([day] + [d for d in history if d != day])[:60])
    return report


def due(db, now: dt.datetime) -> bool:
    local = now.astimezone(ET)
    if local.time() < dt.time(20, 5):
        return False
    latest = _get(db, "nightly_latest")
    return not latest or latest.get("day") != local.date().isoformat()


def collect_equities(db, encryption_key: str) -> dict:
    """Current equity per account from read-only sources; None when unavailable."""
    out = {}
    try:
        from app.brokers import alpaca_connection
        adapter, _ = alpaca_connection.load_read_only_adapter(db, encryption_key, paper=False)
        out["live"] = float(adapter.get_balances()["equity"])
    except Exception:
        out["live"] = None
    books = {}
    try:
        from app.brokers.binance_us_trader import PAIRS, BinanceUSTrader
        t = BinanceUSTrader()
        books = {p: t.book(p)["bid"] for p in PAIRS}
    except Exception:
        pass
    try:
        from app.brokers.binance_us import readiness
        r = readiness(db, encryption_key)
        bal = {b["asset"]: float(b["free"]) + float(b["locked"]) for b in r["balances"]}
        out["binance"] = round(bal.get("USD", 0.0) + sum(bal.get(p.split("/")[0], 0.0) * px for p, px in books.items()), 2)
    except Exception:
        out["binance"] = None
    for mode, start in (("paper", 105.0), ("binance-paper", 100.0)):
        lots = db.query(AllocatorLot).filter_by(mode=mode).all()
        if not lots:
            out[mode] = None
            continue
        realized = sum(((l.exit_price or l.entry_price) - l.entry_price) * l.quantity for l in lots if l.status == "closed")
        unreal = sum((books.get(l.symbol, l.entry_price) - l.entry_price) * l.quantity for l in lots if l.status == "open")
        out[mode] = round(start + realized + unreal, 2)
    return out


def run_if_due(db, encryption_key: str, push=None, now: dt.datetime | None = None) -> dict | None:
    now = now or dt.datetime.now(dt.timezone.utc)
    if not due(db, now):
        return None
    report = build(db, collect_equities(db, encryption_key), now)
    if push:
        title = "Nightly review: all clear" if not report["issues"] else f"Nightly review: {report['issues']} issue(s)"
        live = [l for l, a in zip(report["lines"], report["accounts"]) if "paper" not in a["mode"]]
        push({"title": title, "body": " · ".join(live or report["lines"])[:230], "tag": "nightly"})
    return report


def latest(db) -> dict | None:
    return _get(db, "nightly_latest")


def history(db) -> list[dict]:
    return [r for r in (_get(db, f"nightly:{d}") for d in (_get(db, "nightly_index") or [])) if r]
