"""Reconcile an Agentic entry, broker stop, and flat exit without blind retries.

No strategy worker calls this yet. A Robinhood entry requires its own risk and
validation path before this lifecycle can be connected to real submissions.
"""
from __future__ import annotations

from uuid import uuid4

from app.audit.logger import log_and_commit
from app.brokers.robinhood_execution import RobinhoodOrderTransport
from app.models.models import (OrderIntent, RobinhoodStrategyReadiness,
                               RobinhoodTradeLifecycle, RiskReservation,
                               StrategyValidationRecord, TradeDecisionRecord)


class RobinhoodLifecycleError(RuntimeError):
    pass


def _number(row: dict, *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise RobinhoodLifecycleError(f"Invalid broker {key}") from exc
    return 0.0


def _state(row: dict) -> str:
    return str(row.get("state") or row.get("status") or "").lower()


def _order_id(row: dict) -> str:
    value = row.get("id") or row.get("order_id")
    if not value:
        raise RobinhoodLifecycleError("Broker did not return an order ID")
    return str(value)


def _stop_matches(row: dict, lifecycle: RobinhoodTradeLifecycle) -> bool:
    symbol = str(row.get("symbol") or "").upper().replace("-", "")
    side = str(row.get("side") or "").lower()
    quantity = _number(row, "quantity", "qty")
    price = _number(row, "stop_price", "trigger_price")
    return (symbol == lifecycle.symbol and side == "sell" and
            abs(quantity - lifecycle.quantity) <= 1e-8 and
            abs(price - lifecycle.stop_price) <= 1e-8)


def _position_quantity(transport: RobinhoodOrderTransport, asset_class: str, symbol: str) -> float:
    if asset_class == "equity":
        rows = transport.adapter.get_positions()
    else:
        rows = transport.adapter.get_crypto_positions()
    matches = [row for row in rows if isinstance(row, dict)
               and str(row.get("symbol") or row.get("currency_pair") or "").upper().replace("-", "") == symbol]
    if len(matches) > 1:
        raise RobinhoodLifecycleError("Duplicate broker position")
    return _number(matches[0], "quantity", "qty") if matches else 0.0


def record_entry(db, *, trade_id: str, account_id: str, asset_class: str,
                 symbol: str, quantity: float, stop_price: float, entry_order_id: str) -> RobinhoodTradeLifecycle:
    """Bind a preapproved trade to its exact broker entry before monitoring."""
    trade = db.get(TradeDecisionRecord, trade_id)
    intent = db.query(OrderIntent).filter_by(trade_id=trade_id, account_id=account_id,
                                             broker_order_id=entry_order_id).one_or_none()
    validation = (db.get(StrategyValidationRecord, trade.strategy)
                  if trade is not None else None)
    readiness = (db.get(RobinhoodStrategyReadiness, trade.strategy)
                 if trade is not None else None)
    if (trade is None or trade.status != "open" or
            not isinstance(trade.risk_engine_result, dict) or
            trade.risk_engine_result.get("approved") is not True or
            validation is None or validation.passed is not True or intent is None or
            readiness is None or readiness.asset_class != asset_class or
            readiness.simulated_lifecycle_passed is not True or readiness.enabled is not True or
            not str(trade.strategy or "").startswith(f"robinhood-{asset_class}-") or
            intent.side != "buy" or abs(float(intent.quantity or 0) - quantity) > 1e-8 or
            db.query(RiskReservation).filter_by(account_id=account_id,
                                                decision_id=intent.decision_id,
                                                status="active").first() is None or
            trade.order_id != entry_order_id or trade.symbol != symbol or
            abs(float(trade.position_size or 0) - quantity) > 1e-8 or
            abs(float(trade.stop_price or 0) - stop_price) > 1e-8 or
            trade.asset_class != asset_class or not account_id or
            asset_class not in {"equity", "crypto"} or quantity <= 0 or stop_price <= 0 or
            (asset_class == "equity" and quantity % 1 != 0)):
        raise RobinhoodLifecycleError("Entry has no matching approved trade")
    if db.get(RobinhoodTradeLifecycle, trade_id) is not None:
        raise RobinhoodLifecycleError("Entry lifecycle is already recorded")
    row = RobinhoodTradeLifecycle(
        trade_id=trade_id, account_id=account_id, asset_class=asset_class,
        symbol=symbol.upper().replace("-", ""), quantity=quantity,
        stop_price=stop_price, entry_order_id=entry_order_id,
        stop_ref_id=str(uuid4()), status="entry_pending")
    db.add(row)
    db.commit()
    log_and_commit(db, "robinhood_entry_lifecycle_recorded", {
        "trade_id": trade_id, "asset_class": asset_class, "symbol": row.symbol,
        "entry_order_id": entry_order_id})
    return row


def reconcile_trade(db, transport: RobinhoodOrderTransport, trade_id: str) -> dict:
    """One broker-confirmed lifecycle step; a missing stop never gets retried blindly."""
    row = db.get(RobinhoodTradeLifecycle, trade_id)
    trade = db.get(TradeDecisionRecord, trade_id)
    if row is None or trade is None:
        raise RobinhoodLifecycleError("Trade lifecycle is missing")
    if row.account_id != transport.adapter.designated_account_id:
        raise RobinhoodLifecycleError("Robinhood account mismatch")
    if row.status == "closed":
        return {"status": "closed", "trade_id": trade_id}
    if row.asset_class == "equity":
        get_order = transport.get_equity_order
        preview = transport.preview_equity
        submit = transport.submit_equity
        stop_type = "stop_market"
    elif row.asset_class == "crypto":
        get_order = transport.get_crypto_order
        preview = transport.preview_crypto
        submit = transport.submit_crypto
        stop_type = "stop_loss"
    else:
        raise RobinhoodLifecycleError("Unsupported asset class")

    entry = get_order(row.entry_order_id)
    filled = _number(entry, "filled_quantity", "filled_qty", "cumulative_quantity")
    entry_state = _state(entry)
    if entry_state in {"rejected", "canceled", "cancelled"} and filled == 0:
        if _position_quantity(transport, row.asset_class, row.symbol) != 0:
            return {"status": "safety_failure", "reason": "rejected_entry_has_position", "trade_id": trade_id}
        intent = db.query(OrderIntent).filter_by(trade_id=trade_id, account_id=row.account_id,
                                                 broker_order_id=row.entry_order_id).one_or_none()
        if intent is None:
            return {"status": "safety_failure", "reason": "entry_intent_missing", "trade_id": trade_id}
        row.status = "entry_failed"
        trade.status = "rejected"
        intent.status = "rejected" if entry_state == "rejected" else "canceled"
        db.query(RiskReservation).filter_by(account_id=row.account_id,
                                            decision_id=intent.decision_id,
                                            status="active").update({"status": "released"})
        db.commit()
        return {"status": "entry_failed", "trade_id": trade_id}
    if filled <= 0 and entry_state not in {"filled", "completed"}:
        return {"status": "entry_pending", "trade_id": trade_id}
    if filled <= 0 and entry_state in {"filled", "completed"}:
        filled = row.quantity
    if abs(filled - row.quantity) > 1e-8:
        row.status = "partial_fill_needs_review"
        db.commit()
        return {"status": "safety_failure", "reason": "partial_entry_fill", "trade_id": trade_id}
    price = _number(entry, "average_price", "filled_avg_price", "fill_price")
    if price <= 0:
        return {"status": "safety_failure", "reason": "entry_fill_price_missing", "trade_id": trade_id}
    trade.fill_price = price
    position_qty = _position_quantity(transport, row.asset_class, row.symbol)
    if row.stop_order_id is None and abs(position_qty - row.quantity) > 1e-8:
        return {"status": "safety_failure", "reason": "entry_position_mismatch", "trade_id": trade_id}

    if row.stop_order_id is None:
        if row.status == "stop_unknown":
            found = transport.find_order_by_ref(row.asset_class, row.stop_ref_id)
            if found is None:
                return {"status": "safety_failure", "reason": "stop_submission_unresolved", "trade_id": trade_id}
            row.stop_order_id = _order_id(found)
        elif row.status == "stop_submitting":
            # A process may have crashed immediately before or after the send.
            # Resolve by reference; never issue the same stop again automatically.
            found = transport.find_order_by_ref(row.asset_class, row.stop_ref_id)
            if found is None:
                return {"status": "safety_failure", "reason": "stop_submission_unresolved", "trade_id": trade_id}
            row.stop_order_id = _order_id(found)
        else:
            stop = {"symbol": row.symbol, "side": "sell", "quantity": row.quantity,
                    "order_type": stop_type, "stop_price": row.stop_price}
            preview_result = preview(**stop)
            if not isinstance(preview_result, dict) or preview_result.get("errors") or preview_result.get("rejected"):
                return {"status": "safety_failure", "reason": "stop_preview_rejected", "trade_id": trade_id}
            row.status = "stop_submitting"
            db.commit()
            try:
                submitted = submit(ref_id=row.stop_ref_id, **stop)
                row.stop_order_id = _order_id(submitted)
            except Exception as exc:
                row.status = "stop_unknown"
                row.last_error = type(exc).__name__
                db.commit()
                log_and_commit(db, "robinhood_stop_submission_uncertain", {
                    "trade_id": trade_id, "error_type": type(exc).__name__})
                return {"status": "safety_failure", "reason": "stop_submission_uncertain", "trade_id": trade_id}
        row.status = "stop_submitted"
        db.commit()

    stop_order = get_order(row.stop_order_id)
    stop_state = _state(stop_order)
    if not _stop_matches(stop_order, row):
        return {"status": "safety_failure", "reason": "protective_stop_details_mismatch", "trade_id": trade_id}
    if stop_state in {"rejected", "canceled", "cancelled", "expired"}:
        row.status = "stop_failed"
        db.commit()
        return {"status": "safety_failure", "reason": "protective_stop_inactive", "trade_id": trade_id}
    if stop_state in {"filled", "completed"}:
        if position_qty != 0:
            return {"status": "safety_failure", "reason": "stop_filled_position_not_flat", "trade_id": trade_id}
        exit_qty = _number(stop_order, "filled_quantity", "filled_qty", "cumulative_quantity")
        exit_price = _number(stop_order, "average_price", "filled_avg_price", "fill_price")
        if abs(exit_qty - row.quantity) > 1e-8 or exit_price <= 0:
            return {"status": "safety_failure", "reason": "stop_fill_incomplete", "trade_id": trade_id}
        intent = db.query(OrderIntent).filter_by(trade_id=trade_id, account_id=row.account_id,
                                                 broker_order_id=row.entry_order_id).one_or_none()
        if intent is None:
            return {"status": "safety_failure", "reason": "entry_intent_missing", "trade_id": trade_id}
        trade.status = "closed"
        trade.exit_price = exit_price
        trade.exit_reason = "protective_stop"
        trade.pnl = (exit_price - price) * row.quantity
        trade.r_multiple = trade.pnl / trade.risk_dollars if trade.risk_dollars else None
        row.status = "closed"
        db.query(RiskReservation).filter_by(account_id=row.account_id,
                                            decision_id=intent.decision_id,
                                            status="active").update({"status": "released"})
        db.commit()
        log_and_commit(db, "robinhood_stop_exit_reconciled", {
            "trade_id": trade_id, "entry_order_id": row.entry_order_id,
            "stop_order_id": row.stop_order_id, "realized_pnl": trade.pnl})
        return {"status": "closed", "trade_id": trade_id, "realized_pnl": trade.pnl}
    if stop_state not in {"new", "pending", "queued", "confirmed", "accepted", "open", "partially_filled"}:
        return {"status": "safety_failure", "reason": "stop_status_unknown", "trade_id": trade_id}
    if abs(position_qty - row.quantity) > 1e-8:
        return {"status": "safety_failure", "reason": "protected_position_mismatch", "trade_id": trade_id}
    row.status = "protected"
    db.commit()
    return {"status": "protected", "trade_id": trade_id, "stop_order_id": row.stop_order_id}
