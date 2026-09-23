from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import (OrderIntent, RiskReservation, RobinhoodTradeLifecycle,
                               StrategyValidationRecord, TradeDecisionRecord)
from app.services.robinhood_lifecycle import record_entry, reconcile_trade, RobinhoodLifecycleError


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def prepared(db, asset_class="equity"):
    symbol, quantity = ("F", 1.0) if asset_class == "equity" else ("BTCUSD", 0.001)
    strategy = f"robinhood-{asset_class}-test"
    trade = TradeDecisionRecord(symbol=symbol, asset_class=asset_class, strategy=strategy,
                                direction="long", order_id="entry-1", entry_price=100, stop_price=90,
                                position_size=quantity, status="open",
                                risk_engine_result={"approved": True}, risk_dollars=1)
    db.add(trade)
    db.add(StrategyValidationRecord(strategy=strategy, methodology_version="test",
                                    trades=20, win_rate=.5, total_return=.1,
                                    max_drawdown=.05, passed=True, reasons=[]))
    db.commit()
    db.add(OrderIntent(intent_key="intent-1", decision_id="decision-1", trade_id=trade.trade_id,
                       account_id="agentic", symbol=symbol, side="buy", quantity=quantity,
                       status="filled", broker_order_id="entry-1"))
    db.add(RiskReservation(id="reservation-1", account_id="agentic", decision_id="decision-1",
                           risk_dollars=1, notional=100, status="active"))
    db.commit()
    row = record_entry(db, trade_id=trade.trade_id, account_id="agentic",
                       asset_class=asset_class, symbol=symbol, quantity=quantity,
                       stop_price=90, entry_order_id="entry-1")
    return trade, row


def fake_transport(asset_class="equity", quantity=1.0):
    broker = MagicMock()
    broker.adapter.designated_account_id = "agentic"
    symbol = "F" if asset_class == "equity" else "BTCUSD"
    stop_row = {"id": "stop-1", "state": "accepted", "symbol": symbol,
                "side": "sell", "quantity": quantity, "stop_price": 90}
    broker.get_equity_order.side_effect = lambda order_id: (
        {"id": "entry-1", "state": "filled", "filled_qty": quantity,
         "filled_avg_price": 100} if order_id == "entry-1" else
        stop_row)
    broker.get_crypto_order.side_effect = broker.get_equity_order.side_effect
    broker.adapter.get_positions.return_value = [{"symbol": "F", "qty": quantity}]
    broker.adapter.get_crypto_positions.return_value = [{"symbol": "BTCUSD", "quantity": quantity}]
    broker.submit_equity.return_value = {"id": "stop-1"}
    broker.submit_crypto.return_value = {"id": "stop-1"}
    broker.preview_equity.return_value = {}
    broker.preview_crypto.return_value = {}
    return broker


def test_equity_fill_stop_and_flat_exit_release_only_linked_risk(db):
    trade, row = prepared(db)
    db.add(RiskReservation(id="other", account_id="agentic", decision_id="other",
                           risk_dollars=1, notional=5, status="active"))
    db.commit()
    broker = fake_transport()
    assert reconcile_trade(db, broker, trade.trade_id)["status"] == "protected"
    broker.submit_equity.assert_called_once()
    assert broker.submit_equity.call_args.kwargs["order_type"] == "stop_market"
    assert reconcile_trade(db, broker, trade.trade_id)["status"] == "protected"
    broker.submit_equity.assert_called_once()
    broker.get_equity_order.side_effect = lambda order_id: (
        {"id": "entry-1", "state": "filled", "filled_qty": 1,
         "filled_avg_price": 100} if order_id == "entry-1" else
        {"id": "stop-1", "state": "filled", "symbol": "F", "side": "sell",
         "quantity": 1, "stop_price": 90, "filled_qty": 1,
         "filled_avg_price": 89})
    broker.adapter.get_positions.return_value = []
    assert reconcile_trade(db, broker, trade.trade_id)["status"] == "closed"
    assert trade.exit_price == 89 and trade.pnl == -11
    assert db.get(RiskReservation, "reservation-1").status == "released"
    assert db.get(RiskReservation, "other").status == "active"
    assert reconcile_trade(db, broker, trade.trade_id)["status"] == "closed"


def test_uncertain_crypto_stop_is_not_submitted_twice(db):
    trade, row = prepared(db, "crypto")
    broker = fake_transport("crypto", .001)
    broker.submit_crypto.side_effect = TimeoutError("after send")
    result = reconcile_trade(db, broker, trade.trade_id)
    assert result["reason"] == "stop_submission_uncertain"
    assert row.status == "stop_unknown"
    broker.find_order_by_ref.return_value = None
    assert reconcile_trade(db, broker, trade.trade_id)["reason"] == "stop_submission_unresolved"
    broker.submit_crypto.assert_called_once()
    broker.find_order_by_ref.return_value = {"id": "stop-1"}
    assert reconcile_trade(db, broker, trade.trade_id)["status"] == "protected"
    broker.submit_crypto.assert_called_once()


def test_rejected_stop_and_position_mismatch_block_completion(db):
    trade, row = prepared(db)
    broker = fake_transport()
    broker.adapter.get_positions.return_value = []
    assert reconcile_trade(db, broker, trade.trade_id)["reason"] == "entry_position_mismatch"
    broker.submit_equity.assert_not_called()
    broker.adapter.get_positions.return_value = [{"symbol": "F", "qty": 1}]
    broker.get_equity_order.side_effect = lambda order_id: (
        {"id": "entry-1", "state": "filled", "filled_qty": 1,
         "filled_avg_price": 100} if order_id == "entry-1" else
        {"id": "stop-1", "state": "rejected", "symbol": "F",
         "side": "sell", "quantity": 1, "stop_price": 90})
    assert reconcile_trade(db, broker, trade.trade_id)["reason"] == "protective_stop_inactive"
    assert trade.status == "open"
    assert db.get(RiskReservation, "reservation-1").status == "active"


def test_record_entry_requires_matching_validation_and_risk(db):
    with pytest.raises(RobinhoodLifecycleError, match="matching approved trade"):
        record_entry(db, trade_id="missing", account_id="agentic", asset_class="equity",
                     symbol="F", quantity=1, stop_price=90, entry_order_id="entry-1")


def test_stop_must_match_exact_position_and_price(db):
    trade, row = prepared(db)
    broker = fake_transport()
    broker.get_equity_order.side_effect = lambda order_id: (
        {"id": "entry-1", "state": "filled", "filled_qty": 1,
         "filled_avg_price": 100} if order_id == "entry-1" else
        {"id": "stop-1", "state": "accepted", "symbol": "F", "side": "sell",
         "quantity": 1, "stop_price": 80})
    result = reconcile_trade(db, broker, trade.trade_id)
    assert result["reason"] == "protective_stop_details_mismatch"
    assert db.get(RiskReservation, "reservation-1").status == "active"


def test_filled_stop_does_not_close_while_position_remains(db):
    trade, row = prepared(db)
    broker = fake_transport()
    broker.get_equity_order.side_effect = lambda order_id: (
        {"id": "entry-1", "state": "filled", "filled_qty": 1,
         "filled_avg_price": 100} if order_id == "entry-1" else
        {"id": "stop-1", "state": "filled", "symbol": "F", "side": "sell",
         "quantity": 1, "stop_price": 90, "filled_qty": 1,
         "filled_avg_price": 89})
    assert reconcile_trade(db, broker, trade.trade_id)["reason"] == "stop_filled_position_not_flat"
    assert trade.status == "open"
    assert db.get(RiskReservation, "reservation-1").status == "active"


def test_fractional_equity_cannot_enter_unprotectable_lifecycle(db):
    trade, row = prepared(db)
    with pytest.raises(RobinhoodLifecycleError, match="already recorded"):
        record_entry(db, trade_id=trade.trade_id, account_id="agentic", asset_class="equity",
                     symbol="F", quantity=1, stop_price=90, entry_order_id="entry-1")
    db.delete(row)
    trade.position_size = .5
    db.query(OrderIntent).filter_by(trade_id=trade.trade_id).one().quantity = .5
    db.commit()
    with pytest.raises(RobinhoodLifecycleError, match="matching approved trade"):
        record_entry(db, trade_id=trade.trade_id, account_id="agentic", asset_class="equity",
                     symbol="F", quantity=.5, stop_price=90, entry_order_id="entry-1")
