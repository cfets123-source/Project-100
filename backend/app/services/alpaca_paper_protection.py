"""Create broker-side stops for external Alpaca paper or live positions.

A live position without a recorded stop price halts live trading. A paper
failure blocks the paper worker without changing the live state.
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


def _orders_after_submission_error(adapter, symbol: str, quantity: float) -> tuple[dict | None, bool]:
    """Resolve an uncertain POST against broker state before considering an exit.

    A timeout can occur after Alpaca accepts an order. Sending a market sell
    without this read can leave both the stop and exit active for one position.
    """
    active = {"new", "pending_new", "accepted", "pending", "open", "partially_filled"}
    recovered = None
    pending_exit = False
    for order in adapter.get_orders():
        if (str(order.get("symbol")) == symbol and str(order.get("side")) == "sell"
                and str(order.get("status")) in active):
            if str(order.get("type")) in {"stop", "stop_limit", "trailing_stop"}:
                if float(order.get("qty") or 0) >= quantity - 1e-9:
                    recovered = order
            else:
                pending_exit = True
    return recovered, pending_exit


def _emergency_close_unprotected_position(db, adapter, *, symbol: str, quantity: float,
                                          mode: str, reason: str) -> dict:
    """Submit one protective exit when a filled position cannot be protected.

    The kill switch prevents entries first.  The already-created broker adapter
    is then used for one market exit only; failures are recorded, never retried.
    """
    prefix = f"alpaca_{mode}_unprotected_exit"
    try:
        result = adapter.place_order(OrderRequest(symbol=symbol, side="sell", quantity=quantity))
    except Exception as exc:  # noqa: BLE001 - preserve bounded broker evidence
        detail = f"{type(exc).__name__}: {exc}"[:600]
        log_and_commit(db, f"{prefix}_failed", {"symbol": symbol, "reason": reason,
                                                  "broker_error": detail})
        return {"submitted": False, "reason": reason, "broker_error": detail}
    payload = {"symbol": symbol, "quantity": quantity, "reason": reason,
               "order_id": str(result.order_id), "status": str(result.status)}
    log_and_commit(db, f"{prefix}_submitted", payload)
    return {"submitted": True, **payload}


def ensure_protective_stops(db, adapter, cfg, *, mode: str = "paper") -> dict:
    """Place or renew a sell stop for every externally held long position.

    The caller must supply the separately gated adapter for the selected mode.
    A missing stop blocks another entry; only live failures trip the global
    kill switch.
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
        if symbol in check["pending_exit_symbols"]:
            if mode == "live":
                state.activate_kill_switch(f"live unprotected position has pending exit: {symbol}")
            log_and_commit(db, f"{event_prefix}_exit_pending", {"symbol": symbol})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "exit_pending", "emergency_exit": {"submitted": False}}
        entry = _entry_for_position(db, adapter, symbol, quantity)
        if quantity <= 0 or entry is None:
            if mode == "live":
                state.activate_kill_switch(f"{mode} position without recorded protective stop: {symbol}")
            emergency_exit = _emergency_close_unprotected_position(
                db, adapter, symbol=symbol, quantity=quantity, mode=mode, reason="missing_recorded_stop"
            )
            log_and_commit(db, f"{event_prefix}_failed",
                           {"symbol": symbol, "reason": "missing_recorded_stop"})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "missing_recorded_stop", "emergency_exit": emergency_exit}
        entry_order_id, stop_price = entry
        stop_price = _sell_stop_price_for_broker(stop_price)
        recorded = db.get(ledger, entry_order_id)
        try:
            result = adapter.place_order(OrderRequest(symbol=symbol, side="sell", quantity=quantity,
                                                       order_type="stop", stop_price=stop_price,
                                                       # Alpaca fractional stops are DAY orders; the worker
                                                       # renews and verifies them on every market-session cycle.
                                                       time_in_force="day"))
        except Exception as exc:  # Never retry an uncertain non-idempotent POST.
            detail = f"{type(exc).__name__}: {exc}"[:600]
            try:
                recovered, pending_exit = _orders_after_submission_error(adapter, symbol, quantity)
                if recovered is not None:
                    item = {"symbol": symbol, "order_id": str(recovered["id"]),
                            "stop_price": stop_price, "entry_order_id": entry_order_id}
                    if recorded is None:
                        db.add(ledger(entry_order_id=entry_order_id, symbol=symbol,
                                      quantity=quantity, stop_price=stop_price,
                                      protective_order_id=item["order_id"]))
                    else:
                        recorded.quantity, recorded.stop_price = quantity, stop_price
                        recorded.protective_order_id = item["order_id"]
                    db.commit()
                    log_and_commit(db, f"{event_prefix}_recovered", {**item, "error": detail})
                    placed.append(item)
                    continue
                # Only a successful broker read can establish that no stop exists.
                if mode == "live":
                    state.activate_kill_switch(f"{mode} protective stop failed: {symbol}")
                if pending_exit:
                    log_and_commit(db, f"{event_prefix}_exit_pending", {"symbol": symbol,
                                                                       "error": detail})
                    return {"protected": False, "placed": placed, "failed": symbol,
                            "reason": "exit_pending", "emergency_exit": {"submitted": False}}
            except Exception as read_exc:
                if mode == "live":
                    state.activate_kill_switch(f"{mode} protective stop state unknown: {symbol}")
                read_detail = f"{type(read_exc).__name__}: {read_exc}"[:600]
                log_and_commit(db, f"{event_prefix}_broker_state_unknown",
                               {"symbol": symbol, "error": detail, "read_error": read_detail})
                return {"protected": False, "placed": placed, "failed": symbol,
                        "reason": "broker_state_unknown", "emergency_exit": {"submitted": False}}
            emergency_exit = _emergency_close_unprotected_position(
                db, adapter, symbol=symbol, quantity=quantity, mode=mode, reason="protective_stop_broker_error"
            )
            log_and_commit(db, f"{event_prefix}_failed",
                           {"symbol": symbol, "reason": detail})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "broker_error", "emergency_exit": emergency_exit}
        if result.status not in {"new", "pending_new", "accepted", "pending", "open"} or not result.order_id:
            if mode == "live":
                state.activate_kill_switch(f"{mode} protective stop rejected: {symbol}")
            emergency_exit = _emergency_close_unprotected_position(
                db, adapter, symbol=symbol, quantity=quantity, mode=mode, reason="protective_stop_rejected"
            )
            log_and_commit(db, f"{event_prefix}_failed",
                           {"symbol": symbol, "reason": "rejected", "status": result.status})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "rejected", "emergency_exit": emergency_exit}
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
