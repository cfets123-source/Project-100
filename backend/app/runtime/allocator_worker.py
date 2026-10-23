"""All-in allocator worker (paper or live) for one Alpaca account.

Replaces the single-position Stage Runner worker for that account: it adopts the
existing TQQQ bracket lot as the core, keeps every dollar invested with fractional
orders, and protects each non-bracket lot itself (see strategies/allocator.py).
Live mode additionally requires: owner acceptance of ALLOCATOR_VERSION, system
state LIVE, LIVE_TRADING_ENABLED, and ALLOCATOR_LIVE_ENABLED=true.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import time
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.audit.logger import log_and_commit
from app.brokers.base import OrderRequest
from app.models.models import AllocatorLot, AllocatorState, AuditLogEntry, ScannerSignal
from app.research.multi_market_rules import indicators, rule_exit
from app.strategies.allocator import (
    ALLOCATOR_VERSION, CORE_STOP, CORE_SYMBOL, CORE_TARGET, CORE_WEIGHT, CRYPTO_QTY_DECIMALS, MIN_ORDER_USD,
    SATELLITE_SLOTS, ROTATION_MIN_HOLD_SESSIONS, daily_exit, floor_qty, is_crypto, plan_buys, plan_rotation, price_exit,
)

ET = ZoneInfo("America/New_York")
ACTIVE = {"new", "accepted", "pending_new", "partially_filled", "held"}


def _today(now):
    return now.astimezone(ET).date()


def _in_entry_window(now) -> bool:
    t = now.astimezone(ET).time()
    return dt.time(9, 35) <= t <= dt.time(15, 30)


def _state(db, mode) -> AllocatorState:
    st = db.get(AllocatorState, mode)
    if st is None:
        st = AllocatorState(mode=mode, peak_equity=0.0, halted=False)
        db.add(st)
        db.commit()
    return st


def _open_lots(db, mode):
    return db.query(AllocatorLot).filter_by(mode=mode, status="open").all()


def _pkey(symbol: str) -> str:
    """Alpaca reports crypto positions without the slash (BTC/USD -> BTCUSD)."""
    return symbol.replace("/", "")


def _bars(reader, symbol, start, end):
    if is_crypto(symbol):
        return reader.get_crypto_daily_bars(symbol, start, end)
    return reader.get_daily_bars(symbol, start, end)


_crypto_cache: dict = {"until": 0.0, "ok": False}
_min_qty_cache: dict = {}


def crypto_enabled(adapter) -> bool:
    """Crypto buys only when the Alpaca account has crypto trading active (checked hourly)."""
    if time.time() < _crypto_cache["until"]:
        return _crypto_cache["ok"]
    try:
        ok = str(adapter.get_account_capabilities().get("crypto_status") or "").upper() == "ACTIVE"
    except Exception:
        ok = False
    _crypto_cache.update(until=time.time() + 3600, ok=ok)
    return ok


def _min_qty(adapter, symbol) -> float:
    if symbol not in _min_qty_cache:
        try:
            _min_qty_cache[symbol] = float(adapter.get_asset(symbol).get("min_order_size") or 0)
        except Exception:
            return 0.0
    return _min_qty_cache[symbol]


def _quotes(adapter, symbols) -> dict:
    out = {}
    crypto = [s for s in symbols if is_crypto(s)]
    if crypto:
        for q in adapter.get_crypto_quotes(crypto):
            out[q.symbol] = {"last": q.last, "ask": q.ask or q.last, "bid": q.bid or q.last}
    symbols = [s for s in symbols if not is_crypto(s)]
    for k in range(0, len(symbols), 50):
        for q in adapter.get_quotes(list(symbols[k:k + 50])):
            mid = (q.bid + q.ask) / 2 if q.bid > 0 and q.ask > 0 else 0
            out[q.symbol] = {"last": q.last or mid, "ask": q.ask or q.last, "bid": q.bid or q.last}
    return out


def adopt_bracket_core(db, adapter, mode, positions, orders, today) -> int:
    """Register an existing broker-bracket TQQQ position as the core lot."""
    if any(l.symbol == CORE_SYMBOL and l.broker_bracket for l in _open_lots(db, mode)):
        return 0
    pos = positions.get(CORE_SYMBOL)
    if not pos:
        return 0
    legs = [o for o in orders if o.get("symbol") == CORE_SYMBOL and o.get("side") == "sell"
            and str(o.get("status")) in ACTIVE]
    stop = next((float(o["stop_price"]) for o in legs if o.get("stop_price")), None)
    target = next((float(o["limit_price"]) for o in legs if o.get("type") == "limit" and o.get("limit_price")), None)
    whole = float(int(float(pos["qty"])))
    if stop is None or target is None or whole < 1:
        return 0
    db.add(AllocatorLot(id=str(uuid.uuid4()), mode=mode, sleeve="core", symbol=CORE_SYMBOL,
                        rule="stage-runner", quantity=whole, entry_price=float(pos["avg_entry_price"]),
                        stop_price=stop, target_price=target, max_hold_days=10_000,
                        broker_bracket=True, opened_on=today.isoformat(), status="open"))
    db.commit()
    return 1


def _flatten_orders(orders):
    return list(orders) + [leg for o in orders for leg in (o.get("legs") or [])]


def reconcile(db, adapter, mode, positions) -> list[str]:
    """Confirm fills and close lots the broker no longer holds."""
    closed, broker_closed = [], []
    for lot in _open_lots(db, mode):
        if not lot.confirmed and lot.order_id:
            try:
                o = adapter.get_order_status(lot.order_id)
            except Exception:
                o = {}
            if str(o.get("status")) == "filled" and o.get("filled_avg_price"):
                px = float(o["filled_avg_price"])
                lot.quantity = float(o.get("filled_qty") or lot.quantity)
                pos_qty = float((positions.get(_pkey(lot.symbol)) or {}).get("qty") or 0)
                if is_crypto(lot.symbol) and 0 < pos_qty < lot.quantity:
                    lot.quantity = pos_qty  # crypto fee is taken from the coin received
                stop_pct = 1 - lot.stop_price / lot.entry_price
                tgt_pct = lot.target_price / lot.entry_price - 1
                lot.entry_price, lot.stop_price, lot.target_price = px, px * (1 - stop_pct), px * (1 + tgt_pct)
                lot.confirmed = True
            elif str(o.get("status")) in {"canceled", "expired", "rejected"}:
                lot.status, lot.exit_reason, lot.quantity = "closed", "entry_not_filled", 0.0
                closed.append(lot.symbol)
    held = {}
    for lot in _open_lots(db, mode):
        if lot.confirmed:
            held[lot.symbol] = held.get(lot.symbol, 0.0) + lot.quantity
    for sym, need in held.items():
        have = float((positions.get(_pkey(sym)) or {}).get("qty") or 0)
        if is_crypto(sym) and have >= need * 0.99:
            continue
        if have + 1e-6 < need:  # broker sold something (bracket leg, manual sale)
            for lot in sorted([l for l in _open_lots(db, mode) if l.symbol == sym and l.confirmed],
                              key=lambda l: (not l.broker_bracket, l.quantity)):
                if have + 1e-6 >= need:
                    break
                lot.status, lot.exit_reason = "closed", "broker_exit"
                lot.closed_on = dt.date.today().isoformat()
                need -= lot.quantity
                closed.append(sym)
                broker_closed.append(sym)
    db.commit()
    for sym in broker_closed:
        log_and_commit(db, "allocator_broker_exit", {"mode": mode, "symbol": sym})
    return closed


def sell_lot(db, adapter, lot, reason, price, today) -> dict:
    qty = lot.quantity
    try:
        res = adapter.place_order(OrderRequest(symbol=lot.symbol, side="sell", quantity=qty,
                                               order_type="market",
                                               time_in_force="gtc" if is_crypto(lot.symbol) else "day",
                                               client_order_id=f"alloc-x-{lot.id[:18]}"))
    except Exception as exc:
        log_and_commit(db, "allocator_sell_failed", {"mode": lot.mode, "symbol": lot.symbol, "reason": reason,
                                                     "error": f"{type(exc).__name__}: {exc}"[:300]})
        return {"symbol": lot.symbol, "sold": False}
    lot.status, lot.exit_reason, lot.exit_price, lot.closed_on = "closed", reason, price, today.isoformat()
    db.commit()
    log_and_commit(db, "allocator_sell", {"mode": lot.mode, "symbol": lot.symbol, "qty": qty, "reason": reason,
                                          "price": price, "order_id": res.order_id, "sleeve": lot.sleeve})
    return {"symbol": lot.symbol, "sold": True, "reason": reason}


def latest_signals(db) -> list[dict]:
    """Newest scan's open signals, taken separately for stocks/ETFs and crypto."""
    last = db.query(ScannerSignal.signal_date).order_by(ScannerSignal.signal_date.desc()).first()
    if not last:
        return []
    rows = db.query(ScannerSignal).filter(ScannerSignal.signal_date >= (
        dt.date.fromisoformat(last[0]) - dt.timedelta(days=7)).isoformat(),
        ScannerSignal.status == "waiting_entry").all()
    newest = {}
    for r in rows:
        k = is_crypto(r.symbol)
        newest[k] = max(newest.get(k, ""), r.signal_date)
    return [{"symbol": r.symbol, "rule": r.rule, "momentum_6m": r.momentum_6m, "signal_date": r.signal_date}
            for r in rows if r.signal_date == newest[is_crypto(r.symbol)]]


def _week(today) -> str:
    y, w, _ = today.isocalendar()
    return f"{y}-W{w:02d}"


def _sessions(adapter, start, end) -> list[str]:
    """Exchange trading days in [start, end]; falls back to weekdays when no calendar is available."""
    try:
        days = sorted(str(r["date"])[:10] for r in adapter.get_market_calendar(start.isoformat(), end.isoformat()))
        if days or start == end:
            return days
    except Exception:
        pass
    return [(start + dt.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
            if (start + dt.timedelta(days=i)).weekday() < 5]


def first_session_of_week(adapter, today) -> bool:
    """Backtest (rot.py) swapped only on the week's first trading day (Monday, or Tuesday after a holiday)."""
    days = _sessions(adapter, today - dt.timedelta(days=today.weekday()), today)
    return bool(days) and days[0] == today.isoformat()


def held_sessions(adapter, opened_on: str, today) -> int:
    """Trading days after the buy day, up to and including today."""
    start = dt.date.fromisoformat(opened_on) + dt.timedelta(days=1)
    return len(_sessions(adapter, start, today)) if start <= today else 0


def rotation_due(db, mode, today, adapter=None) -> bool:
    """Once per ISO week, only on the week's first trading day (matches the backtest)."""
    if adapter is not None and not first_session_of_week(adapter, today):
        return False
    week = _week(today)
    rows = (db.query(AuditLogEntry).filter(AuditLogEntry.event_type == "allocator_rotation_check")
            .order_by(AuditLogEntry.timestamp.desc()).limit(40).all())
    return not any(isinstance(r.payload, dict) and r.payload.get("mode") == mode
                   and r.payload.get("week") == week for r in rows)


def momentum_6m(reader, symbol, today) -> float | None:
    start = (today - dt.timedelta(days=220)).isoformat()
    closes = [float(b["close"]) for b in _bars(reader, symbol, start, today.isoformat())
              if str(b["timestamp"])[:10] < today.isoformat()]
    return closes[-1] / closes[-127] - 1 if len(closes) >= 127 and closes[-127] > 0 else None


def weekly_rotation(db, adapter, mode, today, quotes, *, equity, cash) -> list[dict]:
    """Swap weak satellites for clearly stronger new signals when no capacity is left."""
    lots = _open_lots(db, mode)
    sats = [l for l in lots if l.sleeve == "satellite"]
    per_slot = equity * (1 - CORE_WEIGHT) / SATELLITE_SLOTS
    full = len(sats) >= SATELLITE_SLOTS or cash < per_slot * 0.5
    swaps = []
    if full:
        eligible = [l for l in sats if l.confirmed and not l.broker_bracket
                    and held_sessions(adapter, l.opened_on, today) >= ROTATION_MIN_HOLD_SESSIONS]
        held = [{"id": l.id, "symbol": l.symbol, "momentum": momentum_6m(adapter, l.symbol, today)} for l in eligible]
        by_id = {l.id: l for l in eligible}
        for lot_id, sig in plan_rotation(held=held, signals=latest_signals(db)):
            lot = by_id[lot_id]
            res = sell_lot(db, adapter, lot, "rotation", quotes.get(lot.symbol, {}).get("last"), today)
            if res.get("sold"):
                swaps.append({"sold": lot.symbol, "for": sig["symbol"],
                              "for_momentum": round(sig.get("momentum_6m") or 0, 3)})
    log_and_commit(db, "allocator_rotation_check", {"mode": mode, "week": _week(today),
                                                    "capacity_full": full, "swaps": swaps})
    return swaps


def crypto_daily_review(db, adapter, mode, quotes) -> list[dict]:
    """Once per UTC day: time limit / rule exit for crypto satellites (crypto bars are UTC days)."""
    day = dt.datetime.now(dt.timezone.utc).date()
    lots = [l for l in _open_lots(db, mode) if is_crypto(l.symbol) and l.sleeve == "satellite" and l.confirmed]
    if not lots:
        return []
    rows = (db.query(AuditLogEntry).filter(AuditLogEntry.event_type == "allocator_crypto_review")
            .order_by(AuditLogEntry.timestamp.desc()).limit(20).all())
    if any(isinstance(r.payload, dict) and r.payload.get("mode") == mode and r.payload.get("day") == day.isoformat()
           for r in rows):
        return []
    exits = []
    for lot in lots:
        start = (dt.date.fromisoformat(lot.opened_on) - dt.timedelta(days=400)).isoformat()
        bars = [b for b in adapter.get_crypto_daily_bars(lot.symbol, start, day.isoformat())
                if str(b["timestamp"])[:10] < day.isoformat()]
        if len(bars) < 60:
            continue
        held = sum(1 for b in bars if str(b["timestamp"])[:10] > lot.opened_on)
        reason = daily_exit(lot, held, rule_exit(lot.rule, indicators(bars), len(bars) - 1))
        if reason:
            exits.append(sell_lot(db, adapter, lot, reason, quotes.get(lot.symbol, {}).get("last"),
                                  _today(dt.datetime.now(dt.timezone.utc))))
    log_and_commit(db, "allocator_crypto_review", {"mode": mode, "day": day.isoformat(), "exits": exits})
    return exits


def core_trend_up(reader, now) -> bool:
    end = _today(now).isoformat()
    start = (_today(now) - dt.timedelta(days=420)).isoformat()
    bars = [b for b in reader.get_daily_bars("QQQ", start, end) if str(b["timestamp"])[:10] < end]
    if len(bars) < 200:
        return False
    closes = [float(b["close"]) for b in bars]
    return closes[-1] > sum(closes[-200:]) / 200


def run_cycle(db: Session, adapter, *, mode: str, capital_cap: float | None = None,
              floor_equity: float = 50.0, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    today = _today(now)
    market_open = bool(adapter.get_market_clock().get("is_open"))
    st = _state(db, mode)
    if st.halted:
        return {"mode": mode, "reason": "halted", "detail": st.reason}
    crypto_ok = crypto_enabled(adapter)
    has_crypto = any(is_crypto(l.symbol) for l in _open_lots(db, mode))
    if not market_open and not crypto_ok and not has_crypto:
        return {"mode": mode, "reason": "market_closed"}
    positions = {p["symbol"]: p for p in adapter.get_positions()}
    orders = _flatten_orders(adapter.get_orders())
    adopted = adopt_bracket_core(db, adapter, mode, positions, orders, today) if market_open else 0
    closed = reconcile(db, adapter, mode, positions)
    lots = [l for l in _open_lots(db, mode) if market_open or is_crypto(l.symbol)]
    symbols = sorted({l.symbol for l in lots} | ({CORE_SYMBOL} if market_open else set()))
    quotes = _quotes(adapter, symbols)
    exits = []
    for lot in lots:
        if not lot.confirmed:
            continue
        reason = price_exit(lot, quotes.get(lot.symbol, {}).get("last"))
        if reason:
            exits.append(sell_lot(db, adapter, lot, reason, quotes[lot.symbol]["last"], today))
    if market_open and st.last_daily_review != today.isoformat() and _in_entry_window(now):
        for lot in [l for l in _open_lots(db, mode) if l.sleeve == "satellite" and l.confirmed
                    and not is_crypto(l.symbol)]:
            start = (dt.date.fromisoformat(lot.opened_on) - dt.timedelta(days=400)).isoformat()
            bars = [b for b in adapter.get_daily_bars(lot.symbol, start, today.isoformat())
                    if str(b["timestamp"])[:10] < today.isoformat()]
            if len(bars) < 60:
                continue
            held = sum(1 for b in bars if str(b["timestamp"])[:10] > lot.opened_on)
            reason = daily_exit(lot, held, rule_exit(lot.rule, indicators(bars), len(bars) - 1))
            if reason:
                exits.append(sell_lot(db, adapter, lot, reason, quotes.get(lot.symbol, {}).get("last"), today))
        st.last_daily_review = today.isoformat()
        db.commit()
    exits += crypto_daily_review(db, adapter, mode, quotes)
    bal = adapter.get_balances()
    lots = _open_lots(db, mode)
    held_value = sum(l.quantity * quotes.get(l.symbol, {}).get("last", l.entry_price) for l in lots)
    if capital_cap:  # paper: trade a virtual account of capital_cap, not the $100k paper balance
        realized = sum(((l.exit_price or l.entry_price) - l.entry_price) * l.quantity
                       for l in db.query(AllocatorLot).filter_by(mode=mode, status="closed").all())
        cost_open = sum(l.entry_price * l.quantity for l in lots)
        equity = capital_cap + realized + (held_value - cost_open)
        cash = max(0.0, capital_cap + realized - cost_open)
    else:
        equity = float(bal["equity"])
        cash = max(0.0, min(float(bal["cash"]), float(bal.get("buying_power", bal["cash"]))) - 0.50)
    st.peak_equity = max(st.peak_equity or 0.0, equity)
    db.commit()
    buys, rotations = [], []
    stock_window = market_open and _in_entry_window(now)
    if stock_window and rotation_due(db, mode, today, adapter):
        rotations = weekly_rotation(db, adapter, mode, today, quotes, equity=equity, cash=cash)
    if (stock_window or crypto_ok) and equity >= floor_equity:
        all_lots = _open_lots(db, mode)
        core_value = sum(l.quantity * quotes.get(l.symbol, {}).get("last", l.entry_price)
                         for l in all_lots if l.sleeve == "core")
        signals = [x for x in latest_signals(db)
                   if (is_crypto(x["symbol"]) and crypto_ok) or (not is_crypto(x["symbol"]) and stock_window)]
        plan = plan_buys(equity=equity, cash=cash, core_value=core_value,
                         core_trend_up=stock_window and core_trend_up(adapter, now),
                         open_satellites=[l.symbol for l in all_lots if l.sleeve == "satellite"],
                         exclude={l.symbol for l in db.query(AllocatorLot).filter(
                             AllocatorLot.mode == mode,
                             (AllocatorLot.opened_on == today.isoformat())
                             | (AllocatorLot.closed_on == today.isoformat())).all()},
                         signals=signals, peak_equity=st.peak_equity)
        if plan:
            quotes.update(_quotes(adapter, [b.symbol for b in plan]))
        for b in plan:
            ask = quotes.get(b.symbol, {}).get("ask") or 0
            crypto = is_crypto(b.symbol)
            qty = floor_qty(b.notional, ask, CRYPTO_QTY_DECIMALS) if crypto else floor_qty(b.notional, ask)
            if qty <= 0 or qty * ask < MIN_ORDER_USD or (crypto and qty < _min_qty(adapter, b.symbol)):
                continue
            lot_id = str(uuid.uuid4())
            try:
                res = adapter.place_order(OrderRequest(symbol=b.symbol, side="buy", quantity=qty,
                                                       order_type="market",
                                                       time_in_force="gtc" if crypto else "day",
                                                       client_order_id=f"alloc-b-{lot_id[:18]}"))
            except Exception as exc:
                log_and_commit(db, "allocator_buy_failed", {"mode": mode, "symbol": b.symbol,
                                                            "error": f"{type(exc).__name__}: {exc}"[:300]})
                continue
            db.add(AllocatorLot(id=lot_id, mode=mode, sleeve=b.sleeve, symbol=b.symbol, rule=b.rule,
                                quantity=qty, entry_price=ask, stop_price=ask * (1 - b.stop_pct),
                                target_price=ask * (1 + b.target_pct), max_hold_days=b.max_hold,
                                broker_bracket=False, opened_on=today.isoformat(),
                                order_id=res.order_id, confirmed=False, status="open"))
            db.commit()
            log_and_commit(db, "allocator_buy", {"mode": mode, "symbol": b.symbol, "sleeve": b.sleeve, "rule": b.rule,
                                                 "qty": qty, "notional": round(qty * ask, 2),
                                                 "order_id": res.order_id})
            buys.append({"symbol": b.symbol, "sleeve": b.sleeve, "usd": round(qty * ask, 2)})
    return {"mode": mode, "strategy": ALLOCATOR_VERSION, **({} if market_open else {"reason": "market_closed"}),
            "crypto": crypto_ok, "equity": round(equity, 2), "cash": round(cash, 2),
            "open_lots": len(_open_lots(db, mode)), "adopted": adopted, "closed_by_broker": closed,
            "exits": exits, "rotations": rotations, "buys": buys}


def main() -> int:
    from sqlalchemy import create_engine
    from app.brokers.alpaca_connection import load_live_execution_adapter, load_paper_execution_adapter
    from app.core.config import Settings
    from app.db.session import initialize_schema
    from app.services.owner_experiment import require_owner_experiment
    from app.services.state_machine import StateManager

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--mode", choices=("paper", "live"), required=True)
    parser.add_argument("--capital", type=float, default=None, help="paper: virtual account size")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=60)
    args = parser.parse_args()
    cfg = Settings()
    engine = create_engine(args.database)
    initialize_schema(engine)
    while True:
        try:
            with Session(engine) as db:
                if args.mode == "live":
                    rec = require_owner_experiment(db, ALLOCATOR_VERSION)
                    ok, why = StateManager(db, cfg).live_broker_mutation_allowed()
                    if not ok or os.getenv("ALLOCATOR_LIVE_ENABLED", "false").lower() != "true":
                        raise RuntimeError(why or "ALLOCATOR_LIVE_ENABLED is not true")
                    adapter = load_live_execution_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY,
                                                          enabled=bool(cfg.LIVE_TRADING_ENABLED))
                    result = run_cycle(db, adapter, mode="live", floor_equity=rec.floor_equity)
                else:
                    adapter = load_paper_execution_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, enabled=True)
                    result = run_cycle(db, adapter, mode="paper", capital_cap=args.capital or 100.0)
        except Exception as exc:
            result = {"mode": args.mode, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        print(result, flush=True)
        if args.once:
            return 0
        time.sleep(max(20.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
