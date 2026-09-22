"""Create broker-side stops for external Alpaca paper positions.

This is deliberately limited to the explicitly enabled *paper* execution
adapter.  A position without a recorded Project 100 stop price is a halt
condition: guessing a stop from the current price would be unsafe.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from app.audit.logger import log_and_commit
from app.brokers.base import OrderRequest
from app.models.models import ExternalLiveProtection, ExternalPaperProtection, TradeDecisionRecord
from app.services.protective_order_verification import verify_protective_orders
from app.services.state_machine import StateManager


def _sell_stop_price_for_broker(value: float) -> float:
    """Return an Alpaca-valid sell-stop price without loosening protection."""
    price = Decimal(str(value))
    tick = Decimal("0.01") if price >= 1 else Decimal("0.0001")
    return float(price.quantize(tick, rounding=ROUND_DOWN))


def _entry_for_position(db, adapter, symbol: str, quantity: float) -> tuple[str, float] | None:
    """Resolve a position to its exact filled Project 100 entry order.

    Alpaca positions are symbol-aggregated rather than exposing an entry-lot
    identifier.  We therefore reject overlapping entries in the runner and
    require the broker's filled order id to match our recorded decision.
    """
    decision = (db.query(TradeDecisionRecord)
                .filter(TradeDecisionRecord.symbol == symbol,
                        TradeDecisionRecord.direction == "long",
                        TradeDecisionRecord.stop_price.isnot(None),
                        TradeDecisionRecord.position_size >= quantity)
                .order_by(TradeDecisionRecord.timestamp.desc()).first())
    if decision is None:
        return None
    orders = {str(order.get("id")): order for order in adapter.get_orders()}
    entry = orders.get(str(decision.order_id))
    if not entry or str(entry.get("side")) != "buy" or str(entry.get("status")) != "filled":
        return None
    if float(entry.get("filled_qty") or 0) < quantity:
        return None
    return str(decision.order_id), float(decision.stop_price)


def ensure_protective_stops(db, adapter, cfg, *, mode: str = "paper") -> dict:
    """Place or renew a sell stop for every externally held long position.

    The caller must have constructed ``adapter`` through the paper-only,
    execution-gated factory.  Failure halts the system before another entry can
    be considered; this function never applies to a live credential.
    """
    if mode not in {"paper", "live"}:
        raise ValueError("protective-stop mode must be paper or live")
    if mode == "paper" and not getattr(adapter, "paper", False):
        raise RuntimeError("paper protective-stop manager refuses live adapter")
    if mode == "live":
        if getattr(adapter, "paper", True):
            raise RuntimeError("live protective-stop manager refuses paper adapter")
        allowed, reason = StateManager(db, cfg).live_broker_mutation_allowed()
        if not allowed:
            raise RuntimeError(f"live protective-stop manager blocked: {reason}")
    ledger = ExternalPaperProtection if mode == "paper" else ExternalLiveProtection
    event_prefix = f"alpaca_{mode}_protective_stop"
    check = verify_protective_orders(adapter)
    placed: list[dict] = []
    state = StateManager(db, cfg)
    positions = {str(p.get("symbol")): p for p in adapter.get_positions()}
    for symbol in check["uncovered_positions"]:
        position = positions[symbol]
        quantity = abs(float(position.get("qty") or 0))
        entry = _entry_for_position(db, adapter, symbol, quantity)
        if quantity <= 0 or entry is None:
            state.activate_kill_switch(f"paper position without recorded protective stop: {symbol}")
            log_and_commit(db, "alpaca_paper_protective_stop_failed",
                           {"symbol": symbol, "reason": "missing_recorded_stop"})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "missing_recorded_stop"}
        entry_order_id, stop_price = entry
        stop_price = _sell_stop_price_for_broker(stop_price)
        recorded = db.get(ledger, entry_order_id)
        try:
            result = adapter.place_order(OrderRequest(symbol=symbol, side="sell", quantity=quantity,
                                                       order_type="stop", stop_price=stop_price,
                                                       # Alpaca fractional stops are DAY orders; the worker
                                                       # renews and verifies them on every market-session cycle.
                                                       time_in_force="day"))
        except Exception as exc:  # A broker uncertainty is a halt, not a retry.
            state.activate_kill_switch(f"{mode} protective stop failed: {symbol}")
            log_and_commit(db, f"{event_prefix}_failed",
                           {"symbol": symbol, "reason": str(exc)[:600]})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "broker_error"}
        if result.status not in {"new", "pending_new", "accepted", "pending", "open"} or not result.order_id:
            state.activate_kill_switch(f"{mode} protective stop rejected: {symbol}")
            log_and_commit(db, f"{event_prefix}_failed",
                           {"symbol": symbol, "reason": "rejected", "status": result.status})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "rejected"}
        item = {"symbol": symbol, "order_id": result.order_id, "stop_price": stop_price,
                "entry_order_id": entry_order_id}
        placed.append(item)
        if recorded is None:
            db.add(ledger(entry_order_id=entry_order_id, symbol=symbol, quantity=quantity,
                          stop_price=stop_price, protective_order_id=result.order_id))
            event = f"{event_prefix}_placed"
        else:
            # Fractional Alpaca stops are DAY orders.  After expiry, retain the
            # exact entry binding while replacing only the broker stop id.
            recorded.quantity, recorded.stop_price = quantity, stop_price
            recorded.protective_order_id = result.order_id
            event = f"{event_prefix}_renewed"
        db.commit()
        log_and_commit(db, event, item)
    verified = verify_protective_orders(adapter)
    return {**verified, "placed": placed}
