import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401
from app.services.state_machine import StateManager, PAPER, SAFE
from app.services.protective_exit import place_protective_stop
from app.brokers.paper_broker import PaperBrokerAdapter


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_successful_stop_placement_does_not_change_state(db):
    sm = StateManager(db)
    sm.transition(PAPER, "setup")
    broker = MagicMock(spec=PaperBrokerAdapter)
    broker.place_order.return_value = MagicMock(status="accepted", order_id="stop-1", raw=None)
    ok = place_protective_stop(db, broker, sm, "TST", 10.0, 9.5)
    assert ok
    assert sm.get_state() == PAPER


def test_broker_exception_on_stop_placement_enters_safe_mode(db):
    sm = StateManager(db)
    sm.transition(PAPER, "setup")
    broker = MagicMock(spec=PaperBrokerAdapter)
    broker.place_order.side_effect = ConnectionError("broker unreachable")
    ok = place_protective_stop(db, broker, sm, "TST", 10.0, 9.5)
    assert not ok
    assert sm.get_state() == SAFE


def test_rejected_stop_placement_enters_safe_mode(db):
    sm = StateManager(db)
    sm.transition(PAPER, "setup")
    broker = MagicMock(spec=PaperBrokerAdapter)
    broker.place_order.return_value = MagicMock(status="rejected", order_id=None, raw={"reason": "no_liquidity"})
    ok = place_protective_stop(db, broker, sm, "TST", 10.0, 9.5)
    assert not ok
    assert sm.get_state() == SAFE


def test_safe_mode_after_protective_failure_blocks_new_entries(db):
    sm = StateManager(db)
    sm.transition(PAPER, "setup")
    broker = MagicMock(spec=PaperBrokerAdapter)
    broker.place_order.side_effect = ConnectionError("down")
    place_protective_stop(db, broker, sm, "TST", 10.0, 9.5)
    allowed, reason = sm.can_open_new_entries()
    assert not allowed
    assert "safe" in reason
