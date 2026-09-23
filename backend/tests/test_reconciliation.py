import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import OrderIntent
from app.services.reconciliation import reconcile_intent, reconcile_all_pending


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def make_intent(db, quantity=10.0, broker_order_id="ord-1", status="unknown"):
    intent = OrderIntent(intent_key="k1", decision_id="d1", account_id="acct-designated",
                          symbol="TST", side="buy", quantity=quantity, status=status,
                          broker_order_id=broker_order_id)
    db.add(intent)
    db.commit()
    return intent


def test_partial_fill_reconciled(db):
    intent = make_intent(db, quantity=10.0)
    broker = MagicMock()
    broker.get_order_status.return_value = {"status": "partial", "filled_qty": 4.0, "fill_price": 10.0}
    status = reconcile_intent(db, broker, intent)
    assert status == "partial"
    assert intent.quantity_filled == 4.0


def test_cancel_fill_race_resolves_to_filled_never_loses_the_fill(db):
    """A cancel was attempted, but the broker actually filled first. The fill
    must win — we must never report a filled position as canceled."""
    intent = make_intent(db, quantity=10.0)
    broker = MagicMock()
    broker.get_order_status.return_value = {"status": "filled", "filled_qty": 10.0, "fill_price": 10.05}
    status = reconcile_intent(db, broker, intent)
    assert status == "filled"
    assert intent.quantity_filled == 10.0


def test_rejected_order_reconciled_without_resubmission(db):
    intent = make_intent(db, quantity=10.0)
    broker = MagicMock()
    broker.get_order_status.return_value = {"status": "rejected", "filled_qty": 0.0}
    status = reconcile_intent(db, broker, intent)
    assert status == "rejected"
    broker.place_order.assert_not_called()


def test_canceled_order_reconciled(db):
    intent = make_intent(db, quantity=10.0)
    broker = MagicMock()
    broker.get_order_status.return_value = {"status": "canceled", "filled_qty": 0.0}
    status = reconcile_intent(db, broker, intent)
    assert status == "canceled"


def test_missing_broker_order_id_stays_unresolved_and_never_calls_broker(db):
    intent = make_intent(db, broker_order_id=None)
    broker = MagicMock()
    status = reconcile_intent(db, broker, intent)
    assert status == "unknown"
    broker.get_order_status.assert_not_called()
    broker.place_order.assert_not_called()


def test_reconcile_all_pending_only_touches_resolvable_statuses(db):
    make_intent(db, broker_order_id="a", status="unknown")
    resolved_already = OrderIntent(intent_key="k2", decision_id="d2", account_id="acct",
                                    symbol="TST", side="buy", quantity=1.0, status="filled",
                                    broker_order_id="b")
    db.add(resolved_already)
    db.commit()
    broker = MagicMock()
    broker.get_order_status.return_value = {"status": "filled", "filled_qty": 10.0, "fill_price": 10.0}
    results = reconcile_all_pending(db, broker)
    assert len(results) == 1  # the already-filled one is untouched
    assert broker.get_order_status.call_count == 1


def test_pending_new_order_is_reconciled_when_alpaca_reports_a_fill(db):
    make_intent(db, broker_order_id="a", status="pending_new")
    broker = MagicMock()
    broker.get_order_status.return_value = {"status": "filled", "filled_qty": 10.0, "fill_price": 10.0}
    assert reconcile_all_pending(db, broker) == ["filled"]


def test_account_scoped_reconciliation_never_queries_another_broker_account(db):
    make_intent(db, broker_order_id="paper-order", status="pending_new")
    db.add(OrderIntent(intent_key="live", decision_id="live-d", account_id="live-account",
                       symbol="TST", side="buy", quantity=1.0, status="pending_new",
                       broker_order_id="live-order"))
    db.commit()
    broker = MagicMock()
    broker.get_order_status.return_value = {"status": "filled", "filled_qty": 10.0,
                                            "filled_avg_price": "10"}

    assert reconcile_all_pending(db, broker, account_id="acct-designated") == ["filled"]
    broker.get_order_status.assert_called_once_with("paper-order")
    assert db.get(OrderIntent, "live").status == "pending_new"


def test_alpaca_string_fill_quantity_and_price_are_reconciled(db):
    intent = make_intent(db, quantity=0.263462957, status="pending_new")
    broker = MagicMock()
    broker.get_order_status.return_value = {"status": "filled", "filled_qty": "0.263462957",
                                            "filled_avg_price": "126.554"}

    assert reconcile_intent(db, broker, intent) == "filled"
    assert intent.quantity_filled == 0.263462957
