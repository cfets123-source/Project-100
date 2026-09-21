"""Broker-reconciled live position management after the final worker gate."""
from __future__ import annotations

from app.audit.logger import log_and_commit
from app.brokers.base import OrderRequest
from app.models.models import (ExternalLiveExit, ExternalLiveProtection,
                               ExternalPaperExit, ExternalPaperProtection,
                               OrderIntent, RiskReservation, TradeDecisionRecord)

OPEN = {"new", "pending_new", "accepted", "pending", "open"}
FILLED = {"filled", "partially_filled", "partial"}


def _trade(db, entry_order_id: str):
    return (db.query(TradeDecisionRecord)
            .filter(TradeDecisionRecord.order_id == entry_order_id)
            .order_by(TradeDecisionRecord.timestamp.desc()).first())


def _release_reservations(db, trade):
    if trade is None:
        return
    intents = db.query(OrderIntent).filter(OrderIntent.trade_id == trade.trade_id).all()
    for intent in intents:
        for reservation in db.query(RiskReservation).filter(
            RiskReservation.account_id == intent.account_id,
            RiskReservation.decision_id == intent.decision_id,
            RiskReservation.status == "active",
        ):
            reservation.status = "released"


def _finish_trade(db, entry_order_id: str, exit_order: dict, reason: str, mode: str):
    trade = _trade(db, entry_order_id)
    if trade is None or trade.status == "closed":
        return False
    price = float(exit_order.get("filled_avg_price") or exit_order.get("fill_price") or 0)
    quantity = float(exit_order.get("filled_qty") or 0)
    if price <= 0 or quantity <= 0:
        return False
    entry = float(trade.fill_price or trade.entry_price or 0)
    pnl = (price - entry) * quantity
    trade.status, trade.exit_price, trade.exit_reason = "closed", price, reason
    trade.pnl = pnl
    trade.r_multiple = pnl / trade.risk_dollars if trade.risk_dollars else None
    trade.post_trade_analysis = {"mode": "live", "broker_reconciled": True,
                                 "entry_order_id": entry_order_id,
                                 "exit_order_id": str(exit_order.get("id")),
                                 "reason": reason}
    _release_reservations(db, trade)
    db.commit()
    log_and_commit(db, f"alpaca_{mode}_trade_closed", {"trade_id": trade.trade_id,
                   "entry_order_id": entry_order_id, "exit_order_id": str(exit_order.get("id")),
                   "reason": reason, "pnl": pnl})
    return True


def manage_external_positions(db, adapter, *, mode: str) -> dict:
    """Reconcile broker state and autonomously manage recorded broker positions.

    A target order is idempotent through ``ExternalLiveExit``. The stop stays
    live while that order is outstanding. It is cancelled only after the
    broker reports the position flat, preventing an unprotected exit gap.
    """
    if mode not in {"paper", "live"}:
        raise ValueError("mode must be paper or live")
    if bool(getattr(adapter, "paper", False)) != (mode == "paper"):
        raise RuntimeError("position manager broker mode mismatch")
    protection_model = ExternalPaperProtection if mode == "paper" else ExternalLiveProtection
    exit_model = ExternalPaperExit if mode == "paper" else ExternalLiveExit
    event_prefix = f"alpaca_{mode}"
    positions = {str(p.get("symbol")): p for p in adapter.get_positions()
                 if float(p.get("qty") or 0) != 0}
    orders = {str(o.get("id")): o for o in adapter.get_orders()}
    submitted, failed, closed, cancelled = [], [], [], []
    protections = db.query(protection_model).all()
    for protection in protections:
        symbol, entry_id = protection.symbol, protection.entry_order_id
        stop = orders.get(str(protection.protective_order_id))
        exit_row = db.get(exit_model, entry_id)
        if symbol in positions:
            # A stop fill and a still-reported position is an ambiguity. Halt
            # upstream on the next protection verification rather than create
            # a new exit beside it.
            if stop and str(stop.get("status")) in FILLED:
                continue
            trade = _trade(db, entry_id)
            if trade is None or trade.target_price is None:
                continue
            if exit_row is not None:
                broker_exit = orders.get(exit_row.exit_order_id)
                if broker_exit:
                    exit_row.status = str(broker_exit.get("status"))
                    db.commit()
                continue
            quote = next((q for q in adapter.get_quotes([symbol]) if q.symbol == symbol), None)
            if quote is None or quote.last < float(trade.target_price):
                continue
            qty = abs(float(positions[symbol].get("qty") or 0))
            try:
                result = adapter.place_order(OrderRequest(symbol=symbol, side="sell", quantity=qty,
                                                          order_type="market", time_in_force="day"))
            except Exception as exc:
                # The active stop remains in force. A failed target submission
                # is never retried in-process and never removes protection.
                failure = {"symbol": symbol, "entry_order_id": entry_id,
                           "error": type(exc).__name__}
                failed.append(failure)
                log_and_commit(db, f"{event_prefix}_target_exit_failed", failure)
                continue
            if not result.order_id or result.status == "rejected":
                raise RuntimeError(f"live target exit rejected for {symbol}")
            db.add(exit_model(entry_order_id=entry_id, symbol=symbol, quantity=qty,
                                    target_price=float(trade.target_price),
                                    exit_order_id=result.order_id, status=result.status))
            db.commit()
            submitted.append({"symbol": symbol, "entry_order_id": entry_id,
                              "exit_order_id": result.order_id, "status": result.status})
            log_and_commit(db, f"{event_prefix}_target_exit_submitted", submitted[-1])
            continue

        # Flat at broker: resolve a stop/target fill, then cancel any resting
        # exact stop only after flatness is confirmed.
        exit_order = orders.get(exit_row.exit_order_id) if exit_row else None
        if exit_order and str(exit_order.get("status")) in FILLED:
            if _finish_trade(db, entry_id, exit_order, "target_hit", mode):
                closed.append({"symbol": symbol, "reason": "target_hit"})
        elif stop and str(stop.get("status")) in FILLED:
            if _finish_trade(db, entry_id, stop, "stop_hit", mode):
                closed.append({"symbol": symbol, "reason": "stop_hit"})
        if stop and str(stop.get("status")) in OPEN:
            adapter.cancel_order(str(protection.protective_order_id))
            cancelled.append({"symbol": symbol, "stop_order_id": str(protection.protective_order_id)})
            log_and_commit(db, f"{event_prefix}_protective_stop_cancelled", cancelled[-1])
    return {"positions": sorted(positions), "target_exits_submitted": submitted,
            "target_exit_failures": failed,
            "trades_closed": closed, "stops_cancelled": cancelled}


def manage_live_positions(db, adapter) -> dict:
    return manage_external_positions(db, adapter, mode="live")


def manage_paper_positions(db, adapter) -> dict:
    return manage_external_positions(db, adapter, mode="paper")
