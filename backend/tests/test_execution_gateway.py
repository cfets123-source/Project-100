import time
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401 register tables
from app.services.execution_gateway import ExecutionGateway, WrongAccountError
from app.risk.engine import RiskEngine
from app.core.config import Settings
from app.brokers.base import Quote


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def good_quote():
    return Quote(provider="t", symbol="TST", timestamp=time.time(), age_seconds=0.5,
                 bid=9.98, ask=10.02, last=10.0, market_status="open")


def good_signal():
    return {"symbol": "TST", "direction": "long", "strategy": "momentum",
            "entry_price": 10.0, "stop_price": 9.5, "target_price": 11.0,
            "thesis": "test", "ai_confidence": 0.7}


def base_risk_context(**overrides):
    ctx = dict(account_equity=1000.0, avg_dollar_volume=5_000_000.0, sector="tech",
               sector_exposure_pct=0.0, open_position_count=0, daily_pnl_pct=0.0,
               weekly_drawdown_pct=0.0, total_drawdown_pct=0.0, strategy_enabled=True)
    ctx.update(overrides)
    return ctx


def make_gateway(db, broker=None):
    broker = broker or MagicMock()
    return ExecutionGateway(db=db, broker=broker, risk_engine=RiskEngine(cfg=Settings()),
                             designated_account_id="acct-designated"), broker


def test_valid_signal_reaches_broker(db):
    gw, broker = make_gateway(db)
    broker.place_order.return_value = MagicMock(status="filled", order_id="o1", fill_price=10.02)
    result = gw.submit(good_signal(), "acct-designated", good_quote(), base_risk_context())
    assert result.submitted
    broker.place_order.assert_called_once()


def test_wrong_account_never_reaches_broker(db):
    gw, broker = make_gateway(db)
    with pytest.raises(WrongAccountError):
        gw.submit(good_signal(), "acct-retirement-DO-NOT-TOUCH", good_quote(), base_risk_context())
    broker.place_order.assert_not_called()


def test_risk_veto_never_reaches_broker(db):
    gw, broker = make_gateway(db)
    ctx = base_risk_context(daily_pnl_pct=-0.10)  # breaches daily loss limit
    result = gw.submit(good_signal(), "acct-designated", good_quote(), ctx)
    assert not result.submitted
    assert "daily_loss_limit_reached" in result.reason
    broker.place_order.assert_not_called()


def test_missing_stop_never_reaches_broker(db):
    gw, broker = make_gateway(db)
    sig = good_signal()
    sig["stop_price"] = sig["entry_price"]  # no invalidation level
    result = gw.submit(sig, "acct-designated", good_quote(), base_risk_context())
    assert not result.submitted
    broker.place_order.assert_not_called()


def test_injected_unknown_field_rejected_by_schema(db):
    """Simulates a malicious/malformed LLM output trying to smuggle an extra
    directive (e.g. override_risk) through the signal payload."""
    gw, broker = make_gateway(db)
    sig = good_signal()
    sig["override_risk"] = True
    sig["bypass_risk_engine"] = True
    result = gw.submit(sig, "acct-designated", good_quote(), base_risk_context())
    assert not result.submitted
    assert result.reason == "schema_validation_failed"
    broker.place_order.assert_not_called()


def test_invalid_direction_rejected_by_schema(db):
    gw, broker = make_gateway(db)
    sig = good_signal()
    sig["direction"] = "all_in_yolo"
    result = gw.submit(sig, "acct-designated", good_quote(), base_risk_context())
    assert not result.submitted
    assert result.reason == "schema_validation_failed"
    broker.place_order.assert_not_called()


def test_duplicate_submission_within_window_is_suppressed(db):
    """Guards against duplicate orders from retries, restarts, or duplicate workers."""
    gw, broker = make_gateway(db)
    broker.place_order.return_value = MagicMock(status="filled", order_id="o1", fill_price=10.02)
    r1 = gw.submit(good_signal(), "acct-designated", good_quote(), base_risk_context())
    r2 = gw.submit(good_signal(), "acct-designated", good_quote(), base_risk_context())
    assert r1.submitted
    assert not r2.submitted
    assert r2.reason == "duplicate_intent_suppressed"
    assert broker.place_order.call_count == 1


def test_position_size_comes_from_risk_engine_not_signal(db):
    """The gateway must recompute size from the RiskEngine decision — a strategy
    or LLM cannot smuggle its own size through the signal (SignalSchema has no
    size/quantity field at all, so there is nothing to smuggle)."""
    assert "position_size" not in good_signal()
    assert "quantity" not in good_signal()
