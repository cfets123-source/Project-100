"""Read-only reconciliation for one exact Robinhood long-option contract.

No function here submits, replaces, or cancels a broker order. A future entry
worker must persist a validated intent before it can attach an actual fill.
"""
from __future__ import annotations

from math import isfinite
from uuid import UUID

from app.audit.logger import log_and_commit
from app.models.models import (OrderIntent, RiskReservation, RobinhoodOptionLifecycle,
                               RobinhoodStrategyReadiness, StrategyValidationRecord,
                               TradeDecisionRecord)


class RobinhoodOptionLifecycleError(RuntimeError):
    pass


def _positive(row: dict, key: str) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise RobinhoodOptionLifecycleError(f"Invalid broker {key}") from exc
    if not isfinite(value) or value <= 0:
        raise RobinhoodOptionLifecycleError(f"Invalid broker {key}")
    return value


def _quantity(row: dict, key: str) -> int:
    value = _positive(row, key)
    if int(value) != value:
        raise RobinhoodOptionLifecycleError(f"Invalid broker {key}")
    return int(value)


def _leg_matches(order: dict, option_id: str, side: str, effect: str,
                 quantity: int, multiplier: float, symbol: str) -> bool:
    legs = order.get("legs")
    if not isinstance(legs, list) or len(legs) != 1 or not isinstance(legs[0], dict):
        return False
    leg = legs[0]
    try:
        return (leg.get("option_id") == option_id and leg.get("side") == side
                and leg.get("position_effect") == effect
                and _quantity(order, "quantity") == quantity
                and abs(_positive(order, "trade_value_multiplier") - multiplier) < 1e-8
                and order.get("chain_symbol") == symbol)
    except RobinhoodOptionLifecycleError:
        return False


def _intent(db, row: RobinhoodOptionLifecycle) -> OrderIntent | None:
    return db.query(OrderIntent).filter_by(trade_id=row.trade_id,
                                           account_id=row.account_id,
                                           broker_order_id=row.entry_order_id).one_or_none()


def record_option_entry(db, transport, *, trade_id: str, option_id: str,
                        entry_order_id: str, quantity: int, multiplier: float) -> RobinhoodOptionLifecycle:
    """Bind a validated decision, reservation, and one broker entry order."""
    try:
        option_id, entry_order_id = str(UUID(option_id)), str(UUID(entry_order_id))
    except (ValueError, TypeError) as exc:
        raise RobinhoodOptionLifecycleError("Invalid option or entry order ID") from exc
    trade = db.get(TradeDecisionRecord, trade_id)
    if trade is None or not str(trade.strategy or "").startswith("robinhood-option-"):
        raise RobinhoodOptionLifecycleError("Option strategy record is missing")
    validation = db.get(StrategyValidationRecord, trade.strategy)
    readiness = db.get(RobinhoodStrategyReadiness, trade.strategy)
    account_id = transport.adapter.designated_account_id
    intent = db.query(OrderIntent).filter_by(trade_id=trade_id, account_id=account_id,
                                             broker_order_id=entry_order_id).one_or_none()
    if (trade.asset_class != "option" or trade.status != "open" or
            trade.order_id != entry_order_id or trade.direction != "long" or
            not isinstance(trade.risk_engine_result, dict) or
            trade.risk_engine_result.get("approved") is not True or
            validation is None or validation.passed is not True or
            readiness is None or readiness.asset_class != "option" or
            readiness.simulated_lifecycle_passed is not True or readiness.enabled is not True or
            intent is None or intent.side != "buy" or intent.status not in {"submitted", "filled"} or
            int(quantity) != quantity or quantity <= 0 or not isfinite(multiplier) or multiplier <= 0 or
            abs(float(intent.quantity or 0) - quantity) > 1e-8 or
            abs(float(trade.position_size or 0) - quantity) > 1e-8 or
            db.query(RiskReservation).filter_by(account_id=account_id,
                                                decision_id=intent.decision_id,
                                                status="active").one_or_none() is None or
            db.get(RobinhoodOptionLifecycle, trade_id) is not None):
        raise RobinhoodOptionLifecycleError("Option entry has no matching approved intent")
    order = transport.get_option_order(entry_order_id, option_id)
    if not _leg_matches(order, option_id, "buy", "open", quantity, multiplier, trade.symbol):
        raise RobinhoodOptionLifecycleError("Broker entry details mismatch")
    row = RobinhoodOptionLifecycle(trade_id=trade_id, account_id=account_id,
                                   option_id=option_id, underlying_symbol=trade.symbol,
                                   quantity=quantity, multiplier=multiplier,
                                   entry_order_id=entry_order_id, status="entry_pending")
    db.add(row)
    db.commit()
    log_and_commit(db, "robinhood_option_entry_recorded", {
        "trade_id": trade_id, "option_id": option_id,
        "entry_order_id": entry_order_id})
    return row


def bind_protective_exit(db, transport, *, trade_id: str, exit_order_id: str) -> RobinhoodOptionLifecycle:
    """Bind one already-submitted broker stop to the exact long contract."""
    row = db.get(RobinhoodOptionLifecycle, trade_id)
    if row is None or row.exit_order_id is not None or row.account_id != transport.adapter.designated_account_id:
        raise RobinhoodOptionLifecycleError("Option lifecycle cannot bind exit")
    order = transport.get_option_order(exit_order_id, row.option_id)
    if not _leg_matches(order, row.option_id, "sell", "close", row.quantity,
                        row.multiplier, row.underlying_symbol):
        raise RobinhoodOptionLifecycleError("Broker exit details mismatch")
    if order.get("trigger") != "stop" or order.get("state") not in {
            "queued", "confirmed", "partially_filled"}:
        raise RobinhoodOptionLifecycleError("Broker protective stop is not active")
    active = transport.active_option_exit_orders(row.option_id)
    if len(active) != 1 or active[0].get("id") != exit_order_id:
        raise RobinhoodOptionLifecycleError("Duplicate or missing broker exit")
    row.exit_order_id = exit_order_id
    row.status = "stop_recorded"
    db.commit()
    return row


def reconcile_option_trade(db, transport, trade_id: str) -> dict:
    """Reconcile broker fill/flat state; do not present gross P&L as net."""
    row = db.get(RobinhoodOptionLifecycle, trade_id)
    trade = db.get(TradeDecisionRecord, trade_id)
    if row is None or trade is None or row.account_id != transport.adapter.designated_account_id:
        raise RobinhoodOptionLifecycleError("Option lifecycle or account mismatch")
    if row.status in {"entry_failed", "exit_filled_fee_pending", "closed"}:
        return {"status": row.status, "trade_id": trade_id}
    entry = transport.get_option_order(row.entry_order_id, row.option_id)
    if not _leg_matches(entry, row.option_id, "buy", "open", row.quantity,
                        row.multiplier, row.underlying_symbol):
        return {"status": "safety_failure", "reason": "entry_order_mismatch", "trade_id": trade_id}
    position = transport.get_option_position(row.option_id)
    held = float(position["quantity"]) if position else 0.0
    if not isfinite(held) or held < 0 or (position and position.get("type") != "long"):
        return {"status": "safety_failure", "reason": "invalid_option_position", "trade_id": trade_id}
    state = entry.get("state")
    if state in {"rejected", "cancelled", "failed", "voided"}:
        if held != 0 or float(entry.get("processed_quantity") or 0) != 0:
            return {"status": "safety_failure", "reason": "failed_entry_has_exposure", "trade_id": trade_id}
        intent = _intent(db, row)
        if intent is None:
            return {"status": "safety_failure", "reason": "entry_intent_missing", "trade_id": trade_id}
        row.status = "entry_failed"
        trade.status = "rejected"
        intent.status = "rejected"
        db.query(RiskReservation).filter_by(account_id=row.account_id,
                                            decision_id=intent.decision_id,
                                            status="active").update({"status": "released"})
        db.commit()
        return {"status": "entry_failed", "trade_id": trade_id}
    if state in {"queued", "confirmed", "pending_cancelled"} and held == 0:
        return {"status": "entry_pending", "trade_id": trade_id}
    if state != "filled" or float(entry.get("processed_quantity") or 0) != row.quantity:
        return {"status": "safety_failure", "reason": "partial_or_unknown_entry", "trade_id": trade_id}
    entry_price = _positive(entry, "processed_premium") / (row.quantity * row.multiplier)
    trade.fill_price = entry_price
    if row.exit_order_id is None:
        row.status = "unprotected"
        db.commit()
        return {"status": "safety_failure", "reason": "option_fill_without_stop", "trade_id": trade_id}
    exit_order = transport.get_option_order(row.exit_order_id, row.option_id)
    if not _leg_matches(exit_order, row.option_id, "sell", "close", row.quantity,
                        row.multiplier, row.underlying_symbol) or exit_order.get("trigger") != "stop":
        return {"status": "safety_failure", "reason": "protective_exit_mismatch", "trade_id": trade_id}
    exit_state = exit_order.get("state")
    if exit_state in {"rejected", "cancelled", "failed", "voided"}:
        row.status = "stop_failed"
        db.commit()
        return {"status": "safety_failure", "reason": "protective_exit_inactive", "trade_id": trade_id}
    if exit_state == "filled":
        if held != 0 or float(exit_order.get("processed_quantity") or 0) != row.quantity:
            return {"status": "safety_failure", "reason": "exit_fill_not_flat", "trade_id": trade_id}
        intent = _intent(db, row)
        if intent is None:
            return {"status": "safety_failure", "reason": "entry_intent_missing", "trade_id": trade_id}
        exit_price = _positive(exit_order, "processed_premium") / (row.quantity * row.multiplier)
        gross = (exit_price - entry_price) * row.quantity * row.multiplier
        trade.exit_price = exit_price
        trade.exit_reason = "protective_stop"
        trade.post_trade_analysis = {"gross_pnl_before_fees": gross,
                                     "net_pnl_status": "broker_fees_not_verified"}
        trade.pnl = None
        trade.r_multiple = None
        trade.status = "exit_filled_fee_pending"
        row.status = "exit_filled_fee_pending"
        db.query(RiskReservation).filter_by(account_id=row.account_id,
                                            decision_id=intent.decision_id,
                                            status="active").update({"status": "released"})
        db.commit()
        log_and_commit(db, "robinhood_option_exit_flat_fee_pending", {
            "trade_id": trade_id, "option_id": row.option_id,
            "entry_order_id": row.entry_order_id, "exit_order_id": row.exit_order_id,
            "gross_pnl_before_fees": gross})
        return {"status": "exit_filled_fee_pending", "trade_id": trade_id,
                "gross_pnl_before_fees": gross}
    if exit_state not in {"queued", "confirmed", "pending_cancelled"} or held != row.quantity:
        return {"status": "safety_failure", "reason": "partial_or_unprotected_exit", "trade_id": trade_id}
    row.status = "protected"
    db.commit()
    return {"status": "protected", "trade_id": trade_id,
            "stop_order_id": row.exit_order_id}
