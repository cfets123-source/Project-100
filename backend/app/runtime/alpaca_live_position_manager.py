"""Broker-reconciled live position management after the final worker gate."""
from __future__ import annotations
import time

from app.audit.logger import log_and_commit
from app.brokers.base import OrderRequest
from app.models.models import (ExternalLiveExit, ExternalLiveProtection,
                               ExternalPaperExit, ExternalPaperProtection,
                               ExternalTargetExitRetry, OrderIntent, RiskReservation, TradeDecisionRecord)

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


def manage_external_positions(db, adapter, *, mode: str,
                              allow_legacy_target_exit: bool = False) -> dict:
    """Reconcile broker state and autonomously manage recorded broker positions.

    Broker-native bracket orders own normal target/stop management.  A
    separate target-exit POST is therefore disabled by default for legacy
    standalone-stop positions: retrying that path after a 429 only extends the
    broker cooldown.  It remains opt-in for the bounded lifecycle harness.
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
    submitted, deferred, failed, closed, cancelled, legacy_disabled = [], [], [], [], [], []
    # Alpaca aggregates lots by symbol. Project 100 permits one position per
    # symbol, so only the newest still-open recorded entry can manage it.
    # Historical lifecycle evidence must never generate another exit request.
    current_entry = {}
    for symbol in positions:
        trade = (db.query(TradeDecisionRecord)
                 .filter(TradeDecisionRecord.symbol == symbol,
                         TradeDecisionRecord.direction == "long",
                         TradeDecisionRecord.status.in_(("open", "proposed")),
                         TradeDecisionRecord.order_id.isnot(None))
                 .order_by(TradeDecisionRecord.timestamp.desc()).first())
        if trade is not None:
            current_entry[symbol] = str(trade.order_id)
    protections = db.query(protection_model).all()
    for protection in protections:
        symbol, entry_id = protection.symbol, protection.entry_order_id
        if symbol in positions and current_entry.get(symbol) != entry_id:
            continue
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
            if not allow_legacy_target_exit:
                # Existing positions retain their broker-side stop. New
                # entries are brackets, so no second target request is needed.
                legacy_disabled.append({"symbol": symbol, "entry_order_id": entry_id})
                continue
            if exit_row is not None:
                broker_exit = orders.get(exit_row.exit_order_id)
                if broker_exit:
                    exit_row.status = str(broker_exit.get("status"))
                    db.commit()
                continue
            retry = db.get(ExternalTargetExitRetry, entry_id)
            # A failed fractional/simple target close is deliberately terminal
            # for automation.  The active stop remains at the broker; the
            # worker never hammers a second close request into a 429 window.
            if retry is not None and retry.failures < 0:
                legacy_disabled.append({"symbol": symbol, "entry_order_id": entry_id,
                                        "reason": "target_exit_already_failed"})
                continue
            if retry is not None and retry.retry_after > time.time():
                deferred.append({"symbol": symbol, "entry_order_id": entry_id,
                                 "retry_after": retry.retry_after})
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
                if retry is None:
                    retry = ExternalTargetExitRetry(entry_order_id=entry_id, mode=mode,
                                                     retry_after=time.time(), failures=-1)
                    db.add(retry)
                else:
                    retry.failures = -1
                    retry.retry_after = time.time()
                db.commit()
                log_and_commit(db, f"{event_prefix}_target_exit_failed", failure)
                continue
            if not result.order_id or result.status == "rejected":
                raise RuntimeError(f"live target exit rejected for {symbol}")
            db.add(exit_model(entry_order_id=entry_id, symbol=symbol, quantity=qty,
                                    target_price=float(trade.target_price),
                                    exit_order_id=result.order_id, status=result.status))
            if retry is not None:
                db.delete(retry)
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
            "target_exit_deferred": deferred, "target_exit_failures": failed,
            "trades_closed": closed, "stops_cancelled": cancelled,
            "legacy_target_management_disabled": legacy_disabled}


def manage_live_positions(db, adapter, *, allow_legacy_target_exit: bool = False) -> dict:
    return manage_external_positions(db, adapter, mode="live",
                                     allow_legacy_target_exit=allow_legacy_target_exit)


def manage_paper_positions(db, adapter, *, allow_legacy_target_exit: bool = False) -> dict:
    return manage_external_positions(db, adapter, mode="paper",
                                     allow_legacy_target_exit=allow_legacy_target_exit)


def reconcile_broker_bracket_exits(db, adapter, *, mode: str) -> dict:
    """Close trade records from broker-owned bracket legs without a mutation.

    Alpaca exposes a bracket's child orders through ``nested=true``.  The
    target limit and stop legs are mutually exclusive at the broker, so this
    is the authoritative source for a completed exit.
    """
    if mode not in {"paper", "live"}:
        raise ValueError("mode must be paper or live")
    orders = adapter.get_orders()
    by_id = {str(order.get("id")): order for order in orders}
    closed = []
    trades = db.query(TradeDecisionRecord).filter(
        TradeDecisionRecord.status == "open", TradeDecisionRecord.order_id.isnot(None)
    ).all()
    for trade in trades:
        parent = by_id.get(str(trade.order_id), {})
        legs = parent.get("legs") or [order for order in orders
                                       if str(order.get("parent_order_id")) == str(trade.order_id)]
        for leg in legs:
            if str(leg.get("status")) not in FILLED:
                continue
            reason = "target_hit" if str(leg.get("type")) == "limit" else "stop_hit"
            if _finish_trade(db, str(trade.order_id), leg, reason, mode):
                closed.append({"symbol": trade.symbol, "entry_order_id": str(trade.order_id),
                               "exit_order_id": str(leg.get("id")), "reason": reason})
            break
    return {"bracket_trades_closed": closed}
