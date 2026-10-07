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
    ALLOCATOR_VERSION, CORE_STOP, CORE_SYMBOL, CORE_TARGET, CORE_WEIGHT, MIN_ORDER_USD, SATELLITE_SLOTS,
    daily_exit, floor_qty, plan_buys, plan_rotation, price_exit,
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


def _quotes(adapter, symbols) -> dict:
    out = {}
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
    closed = []
    for lot in _open_lots(db, mode):
        if not lot.confirmed and lot.order_id:
            try:
                o = adapter.get_order_status(lot.order_id)
            except Exception:
                o = {}
            if str(o.get("status")) == "filled" and o.get("filled_avg_price"):
                px = float(o["filled_avg_price"])
                lot.quantity = float(o.get("filled_qty") or lot.quantity)
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
        have = float((positions.get(sym) or {}).get("qty") or 0)
        if have + 1e-6 < need:  # broker sold something (bracket leg, manual sale)
            for lot in sorted([l for l in _open_lots(db, mode) if l.symbol == sym and l.confirmed],
                              key=lambda l: (not l.broker_bracket, l.quantity)):
                if have + 1e-6 >= need:
                    break
                lot.status, lot.exit_reason = "closed", "broker_exit"
                lot.closed_on = dt.date.today().isoformat()
                need -= lot.quantity
                closed.append(sym)
    db.commit()
    return closed


def sell_lot(db, adapter, lot, reason, price, today) -> dict:
    qty = lot.quantity
    try:
        res = adapter.place_order(OrderRequest(symbol=lot.symbol, side="sell", quantity=qty,
                                               order_type="market", time_in_force="day",
                                               client_order_id=f"alloc-x-{lot.id[:18]}"))
    except Exception as exc:
        log_and_commit(db, "allocator_sell_failed", {"symbol": lot.symbol, "reason": reason,
                                                     "error": f"{type(exc).__name__}: {exc}"[:300]})
        return {"symbol": lot.symbol, "sold": False}
    lot.status, lot.exit_reason, lot.exit_price, lot.closed_on = "closed", reason, price, today.isoformat()
    db.commit()
    log_and_commit(db, "allocator_sell", {"symbol": lot.symbol, "qty": qty, "reason": reason,
                                          "price": price, "order_id": res.order_id, "sleeve": lot.sleeve})
    return {"symbol": lot.symbol, "sold": True, "reason": reason}


def latest_signals(db) -> list[dict]:
    last = db.query(ScannerSignal.signal_date).order_by(ScannerSignal.signal_date.desc()).first()
    if not last:
        return []
    rows = db.query(ScannerSignal).filter(ScannerSignal.signal_date == last[0],
                                          ScannerSignal.status == "waiting_entry").all()
    return [{"symbol": r.symbol, "rule": r.rule, "momentum_6m": r.momentum_6m, "signal_date": r.signal_date}
            for r in rows]


def _week(today) -> str:
    y, w, _ = today.isocalendar()
    return f"{y}-W{w:02d}"


def rotation_due(db, mode, today) -> bool:
    """Once per ISO week (first trading-day cycle in the entry window)."""
    week = _week(today)
    rows = (db.query(AuditLogEntry).filter(AuditLogEntry.event_type == "allocator_rotation_check")
            .order_by(AuditLogEntry.timestamp.desc()).limit(40).all())
    return not any(isinstance(r.payload, dict) and r.payload.get("mode") == mode
                   and r.payload.get("week") == week for r in rows)


def momentum_6m(reader, symbol, today) -> float | None:
    start = (today - dt.timedelta(days=220)).isoformat()
    closes = [float(b["close"]) for b in reader.get_daily_bars(symbol, start, today.isoformat())
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
        eligible = [l for l in sats if l.confirmed and not l.broker_bracket and l.opened_on != today.isoformat()]
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
    clock = adapter.get_market_clock()
    if not clock.get("is_open"):
        return {"mode": mode, "reason": "market_closed"}
    st = _state(db, mode)
    if st.halted:
        return {"mode": mode, "reason": "halted", "detail": st.reason}
    positions = {p["symbol"]: p for p in adapter.get_positions()}
    orders = _flatten_orders(adapter.get_orders())
    adopted = adopt_bracket_core(db, adapter, mode, positions, orders, today)
    closed = reconcile(db, adapter, mode, positions)
    lots = _open_lots(db, mode)
    symbols = sorted({l.symbol for l in lots} | {CORE_SYMBOL})
    quotes = _quotes(adapter, symbols)
    exits = []
    for lot in lots:
        if not lot.confirmed:
            continue
        reason = price_exit(lot, quotes.get(lot.symbol, {}).get("last"))
        if reason:
            exits.append(sell_lot(db, adapter, lot, reason, quotes[lot.symbol]["last"], today))
    if st.last_daily_review != today.isoformat() and _in_entry_window(now):
        for lot in [l for l in _open_lots(db, mode) if l.sleeve == "satellite" and l.confirmed]:
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
    if _in_entry_window(now) and rotation_due(db, mode, today):
        rotations = weekly_rotation(db, adapter, mode, today, quotes, equity=equity, cash=cash)
    if _in_entry_window(now) and equity >= floor_equity:
        core_value = sum(l.quantity * quotes.get(l.symbol, {}).get("last", l.entry_price)
                         for l in lots if l.sleeve == "core")
        plan = plan_buys(equity=equity, cash=cash, core_value=core_value,
                         core_trend_up=core_trend_up(adapter, now),
                         open_satellites=[l.symbol for l in lots if l.sleeve == "satellite"],
                         exclude={l.symbol for l in db.query(AllocatorLot).filter(
                             AllocatorLot.mode == mode,
                             (AllocatorLot.opened_on == today.isoformat())
                             | (AllocatorLot.closed_on == today.isoformat())).all()},
                         signals=latest_signals(db), peak_equity=st.peak_equity)
        if plan:
            quotes.update(_quotes(adapter, [b.symbol for b in plan]))
        for b in plan:
            ask = quotes.get(b.symbol, {}).get("ask") or 0
            qty = floor_qty(b.notional, ask)
            if qty <= 0 or qty * ask < MIN_ORDER_USD:
                continue
            lot_id = str(uuid.uuid4())
            try:
                res = adapter.place_order(OrderRequest(symbol=b.symbol, side="buy", quantity=qty,
                                                       order_type="market", time_in_force="day",
                                                       client_order_id=f"alloc-b-{lot_id[:18]}"))
            except Exception as exc:
                log_and_commit(db, "allocator_buy_failed", {"symbol": b.symbol,
                                                            "error": f"{type(exc).__name__}: {exc}"[:300]})
                continue
            db.add(AllocatorLot(id=lot_id, mode=mode, sleeve=b.sleeve, symbol=b.symbol, rule=b.rule,
                                quantity=qty, entry_price=ask, stop_price=ask * (1 - b.stop_pct),
                                target_price=ask * (1 + b.target_pct), max_hold_days=b.max_hold,
                                broker_bracket=False, opened_on=today.isoformat(),
                                order_id=res.order_id, confirmed=False, status="open"))
            db.commit()
            log_and_commit(db, "allocator_buy", {"symbol": b.symbol, "sleeve": b.sleeve, "rule": b.rule,
                                                 "qty": qty, "notional": round(qty * ask, 2),
                                                 "order_id": res.order_id})
            buys.append({"symbol": b.symbol, "sleeve": b.sleeve, "usd": round(qty * ask, 2)})
    return {"mode": mode, "strategy": ALLOCATOR_VERSION, "equity": round(equity, 2), "cash": round(cash, 2),
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
