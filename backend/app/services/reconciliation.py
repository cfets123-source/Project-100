"""
Resolves order intents left in an UNKNOWN or otherwise unresolved state (e.g. the
broker connection dropped after place_order was called but before a response was
received). This module NEVER calls broker.place_order — reconciliation only reads
broker state and updates our own records to match reality.
"""
from sqlalchemy.orm import Session
from app.models.models import OrderIntent
from app.brokers.base import BrokerAdapter
from app.audit.logger import log_and_commit

RESOLVABLE_STATUSES = {"pending", "submitted", "unknown"}


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
    filled_qty = status.get("filled_qty", 0.0) or 0.0
    fill_price = status.get("fill_price")

    # A fill always wins over a concurrent cancel attempt — we never discard a real fill.
    if broker_status == "filled" or filled_qty >= intent.quantity:
        intent.status = "filled"
        intent.quantity_filled = intent.quantity
    elif broker_status == "partial" or (0 < filled_qty < intent.quantity):
        intent.status = "partial"
        intent.quantity_filled = filled_qty
    elif broker_status == "rejected":
        intent.status = "rejected"
    elif broker_status == "canceled":
        intent.status = "canceled"
    else:
        intent.status = "unknown"

    db.commit()
    log_and_commit(db, "reconciliation_resolved", {
        "intent_key": intent.intent_key, "resolved_status": intent.status,
        "quantity_filled": intent.quantity_filled, "fill_price": fill_price,
    })
    return intent.status


def reconcile_all_pending(db: Session, broker: BrokerAdapter) -> list[str]:
    pending = db.query(OrderIntent).filter(OrderIntent.status.in_(RESOLVABLE_STATUSES)).all()
    return [reconcile_intent(db, broker, i) for i in pending]
