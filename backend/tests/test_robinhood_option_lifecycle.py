"""Exact-contract Robinhood option reconciliation without broker writes."""
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import (OrderIntent, RiskReservation, RobinhoodOptionLifecycle,
                               RobinhoodStrategyReadiness, StrategyValidationRecord,
                               TradeDecisionRecord)
from app.services.robinhood_option_lifecycle import (
    RobinhoodOptionLifecycleError, bind_protective_exit,
    record_option_entry, reconcile_option_trade)


@pytest.fixture
def setup():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    option_id, entry_id, stop_id = str(uuid4()), str(uuid4()), str(uuid4())
    strategy = "robinhood-option-simulated-v1"
    trade = TradeDecisionRecord(symbol="SPY", asset_class="option", strategy=strategy,
                                direction="long", order_id=entry_id, position_size=1,
                                risk_engine_result={"approved": True}, status="open")
    db.add_all([
        trade,
        StrategyValidationRecord(strategy=strategy, methodology_version="simulated",
                                 trades=20, win_rate=.5, total_return=.1,
                                 max_drawdown=.1, passed=True, reasons=[]),
        RobinhoodStrategyReadiness(strategy=strategy, asset_class="option",
                                   simulated_lifecycle_passed=True, enabled=True),
    ])
    db.commit()
    db.add_all([
        OrderIntent(intent_key="option-intent", decision_id="option-decision",
                    trade_id=trade.trade_id, account_id="agentic", symbol="SPY",
                    side="buy", quantity=1, status="submitted", broker_order_id=entry_id),
        RiskReservation(id="option-reservation", account_id="agentic",
                        decision_id="option-decision", risk_dollars=20,
                        notional=40, status="active"),
    ])
    db.commit()
    broker = MagicMock()
    broker.adapter.designated_account_id = "agentic"
    entry = {"id": entry_id, "chain_symbol": "SPY", "quantity": "1",
             "trade_value_multiplier": "100", "state": "confirmed",
             "processed_quantity": "0", "processed_premium": "0",
             "legs": [{"option_id": option_id, "side": "buy", "position_effect": "open"}]}
    stop = {"id": stop_id, "chain_symbol": "SPY", "quantity": "1",
            "trade_value_multiplier": "100", "state": "confirmed",
            "processed_quantity": "0", "processed_premium": "0", "trigger": "stop",
            "legs": [{"option_id": option_id, "side": "sell", "position_effect": "close"}]}
    broker.get_option_order.side_effect = lambda order_id, contract_id: (
        entry if order_id == entry_id else stop)
    broker.get_option_position.return_value = None
    broker.active_option_exit_orders.return_value = [stop]
    yield db, trade, broker, entry, stop, option_id, entry_id, stop_id
    db.close()


def _record(setup):
    db, trade, broker, _entry, _stop, option_id, entry_id, _stop_id = setup
    return record_option_entry(db, broker, trade_id=trade.trade_id,
                               option_id=option_id, entry_order_id=entry_id,
                               quantity=1, multiplier=100)


def test_option_fill_stop_and_flat_exit_release_reservation_without_invented_net_pnl(setup):
    db, trade, broker, entry, stop, option_id, _entry_id, stop_id = setup
    row = _record(setup)
    assert row.option_id == option_id
    bind_protective_exit(db, broker, trade_id=trade.trade_id, exit_order_id=stop_id)
    assert reconcile_option_trade(db, broker, trade.trade_id)["status"] == "entry_pending"
    entry.update(state="filled", processed_quantity="1", processed_premium="40")
    broker.get_option_position.return_value = {"option_id": option_id, "quantity": "1",
                                                "type": "long"}
    assert reconcile_option_trade(db, broker, trade.trade_id)["status"] == "protected"
    stop.update(state="filled", processed_quantity="1", processed_premium="52")
    broker.get_option_position.return_value = None
    result = reconcile_option_trade(db, broker, trade.trade_id)
    assert result["status"] == "exit_filled_fee_pending"
    assert result["gross_pnl_before_fees"] == pytest.approx(12)
    assert trade.fill_price == pytest.approx(.4) and trade.exit_price == pytest.approx(.52)
    assert trade.pnl is None and trade.status == "exit_filled_fee_pending"
    assert db.get(RiskReservation, "option-reservation").status == "released"
    assert reconcile_option_trade(db, broker, trade.trade_id)["status"] == "exit_filled_fee_pending"
    assert broker.method_calls and all(call[0] not in {
        "submit_long_option", "cancel_option"} for call in broker.method_calls)


def test_option_fill_without_bound_stop_is_explicit_safety_failure(setup):
    db, trade, broker, entry, _stop, option_id, _entry_id, _stop_id = setup
    _record(setup)
    entry.update(state="filled", processed_quantity="1", processed_premium="40")
    broker.get_option_position.return_value = {"option_id": option_id, "quantity": "1",
                                                "type": "long"}
    result = reconcile_option_trade(db, broker, trade.trade_id)
    assert result["reason"] == "option_fill_without_stop"
    assert db.get(RobinhoodOptionLifecycle, trade.trade_id).status == "unprotected"
    assert db.get(RiskReservation, "option-reservation").status == "active"


def test_option_duplicate_exit_and_partial_fill_fail_closed(setup):
    db, trade, broker, entry, stop, option_id, _entry_id, stop_id = setup
    _record(setup)
    broker.active_option_exit_orders.return_value = [stop, {**stop, "id": str(uuid4())}]
    with pytest.raises(RobinhoodOptionLifecycleError, match="Duplicate"):
        bind_protective_exit(db, broker, trade_id=trade.trade_id, exit_order_id=stop_id)
    broker.active_option_exit_orders.return_value = [stop]
    bind_protective_exit(db, broker, trade_id=trade.trade_id, exit_order_id=stop_id)
    entry.update(state="partially_filled", processed_quantity="0.5", processed_premium="20")
    broker.get_option_position.return_value = {"option_id": option_id, "quantity": "0.5",
                                                "type": "long"}
    assert reconcile_option_trade(db, broker, trade.trade_id)["reason"] == "partial_or_unknown_entry"
    assert db.get(RiskReservation, "option-reservation").status == "active"


def test_rejected_option_entry_releases_only_its_reservation(setup):
    db, trade, broker, entry, _stop, _option_id, _entry_id, _stop_id = setup
    _record(setup)
    db.add(RiskReservation(id="other-reservation", account_id="agentic",
                           decision_id="other", risk_dollars=5, notional=5,
                           status="active"))
    db.commit()
    entry["state"] = "rejected"
    assert reconcile_option_trade(db, broker, trade.trade_id)["status"] == "entry_failed"
    assert db.get(RiskReservation, "option-reservation").status == "released"
    assert db.get(RiskReservation, "other-reservation").status == "active"
