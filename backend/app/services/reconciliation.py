"""
Resolves order intents left in an UNKNOWN or otherwise unresolved state (e.g. the
broker connection dropped after place_order was called but before a response was
received). This module NEVER calls broker.place_order — reconciliation only reads
broker state and updates our own records to match reality.
"""
from sqlalchemy.orm import Session
from app.db.transactions import persist
from app.models.models import OrderIntent, TradeDecisionRecord
from app.brokers.base import BrokerAdapter
from app.audit.logger import log_and_commit

# Alpaca may return ``pending_new`` immediately after a submission.  It is a
# broker-pending state, not a terminal state; omitting it leaves a real fill
# stranded in the local ledger and prevents a completed paper lifecycle from
# being proved.
RESOLVABLE_STATUSES = {"pending", "pending_new", "new", "open", "submitted", "accepted", "partial", "unknown"}


def reconcile_intent(db: Session, broker: BrokerAdapter, intent: OrderIntent) -> str:
    if intent.broker_order_id is None:
        # We never even received a broker order id back — nothing to query.
        # Leave as 'unknown'; an operator/alert must investigate (documented limitation:
        # there is no idempotency-key lookup on the broker side implemented here).
        log_and_commit(db, "reconciliation_unresolved", {"intent_key": intent.intent_key,
                                                           "reason": "no_broker_order_id"})
        return intent.status

    status = broker.get_order_status(intent.broker_order_id)
    broker_status = status.get("status")
    filled_qty = float(status.get("filled_qty") or 0.0)
    fill_price = status.get("filled_avg_price") or status.get("fill_price")

    # A fill always wins over a concurrent cancel attempt — we never discard a real fill.
    if broker_status == "filled" or filled_qty >= intent.quantity:
        intent.status = "filled"
        intent.quantity_filled = intent.quantity
        if fill_price is not None and intent.trade_id:
            trade = db.get(TradeDecisionRecord, intent.trade_id)
            if trade is not None and trade.fill_price is None:
                trade.fill_price = float(fill_price)
    elif broker_status in ("partial", "partially_filled") or (0 < filled_qty < intent.quantity):
        intent.status = "partial"
        intent.quantity_filled = filled_qty
    elif broker_status == "rejected":
        intent.status = "rejected"
    elif broker_status in ("canceled", "expired"):
        intent.status = "canceled"
    elif broker_status in ("new", "pending_new", "accepted", "submitted", "pending", "open"):
        intent.status = broker_status
    else:
        intent.status = "unknown"

    persist(db)
    log_and_commit(db, "reconciliation_resolved", {
        "intent_key": intent.intent_key, "resolved_status": intent.status,
        "quantity_filled": intent.quantity_filled, "fill_price": fill_price,
    })
    return intent.status


def reconcile_all_pending(db: Session, broker: BrokerAdapter, *, account_id: str | None = None) -> list[str]:
    pending_query = db.query(OrderIntent).filter(OrderIntent.status.in_(RESOLVABLE_STATUSES))
    if account_id is not None:
        pending_query = pending_query.filter(OrderIntent.account_id == account_id)
    pending = pending_query.all()
    return [reconcile_intent(db, broker, i) for i in pending]
