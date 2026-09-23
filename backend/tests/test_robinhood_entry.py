import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.brokers.base import Quote
from app.core.config import Settings, TradingMode, AutonomyLevel
from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import (OrderIntent, RiskReservation, RobinhoodStrategyReadiness,
                               RobinhoodTradeLifecycle, StrategyValidationRecord, SystemStateRecord)
from app.services.robinhood_entry import submit_validated_entry, recover_uncertain_entry


def setup(asset_class="equity"):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(SystemStateRecord(id="current", state="live"))
    strategy = f"robinhood-{asset_class}-test"
    db.add(StrategyValidationRecord(strategy=strategy, methodology_version="test",
                                    trades=30, win_rate=.5, total_return=.1,
                                    max_drawdown=.05, passed=True, reasons=[]))
    db.add(RobinhoodStrategyReadiness(strategy=strategy, asset_class=asset_class,
                                      simulated_lifecycle_passed=True, enabled=True))
    db.commit()
    cfg = Settings(TRADING_MODE=TradingMode.LIVE,
                   AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS,
                   LIVE_TRADING_ENABLED=True,
                   ROBINHOOD_EQUITY_EXECUTION_ENABLED=asset_class == "equity",
                   ROBINHOOD_CRYPTO_EXECUTION_ENABLED=asset_class == "crypto")
    broker = MagicMock()
    broker.allow_equity = asset_class == "equity"
    broker.allow_crypto = asset_class == "crypto"
    broker.adapter.designated_account_id = "agentic"
    broker.adapter.get_positions.return_value = []
    broker.adapter.get_crypto_positions.return_value = []
    broker.adapter.get_orders.return_value = []
    broker.adapter.get_crypto_orders.return_value = []
    broker.adapter.get_balances.return_value = {"equity": 100, "cash": 100}
    broker.adapter.get_buying_power.return_value = 100
    broker.adapter.get_crypto_buying_power.return_value = 100
    broker.adapter.get_quotes.return_value = [Quote("robinhood_mcp", "F", time.time(), 0,
                                                    9.99, 10.01, 10, "open")]
    broker.adapter.get_crypto_quotes.return_value = [{"symbol": "BTCUSD", "valid_for_execution": True,
                                                       "as_of": datetime.now(timezone.utc).isoformat(),
                                                       "age_seconds": 0, "bid": 9.99,
                                                       "ask": 10.01, "mark": 10}]
    broker.preview_equity.return_value = {}
    broker.preview_crypto.return_value = {}
    broker.submit_equity.return_value = {"id": "entry-1"}
    broker.submit_crypto.return_value = {"id": "entry-1"}
    signal = {"symbol": "F" if asset_class == "equity" else "BTCUSD",
              "direction": "long", "strategy": strategy, "decision_id": "d1",
              "entry_price": 10, "stop_price": 9.5, "target_price": 11}
    return db, cfg, broker, signal


def call(db, cfg, broker, signal, asset_class="equity"):
    return submit_validated_entry(db, broker, cfg, raw_signal=signal,
                                  asset_class=asset_class, avg_dollar_volume=10_000_000,
                                  sector=None, daily_pnl_pct=0, weekly_drawdown_pct=0,
                                  total_drawdown_pct=0)


def test_entry_creates_durable_intent_and_lifecycle_once():
    db, cfg, broker, signal = setup()
    result = call(db, cfg, broker, signal)
    assert result.status == "submitted"
    assert result.order_id == "entry-1"
    assert db.query(OrderIntent).count() == 1
    assert db.get(RobinhoodTradeLifecycle, result.trade_id).stop_price == 9.5
    assert db.query(RiskReservation).filter_by(status="active").count() == 1
    assert call(db, cfg, broker, signal).reason == "duplicate_decision"
    broker.submit_equity.assert_called_once()
    db.close()


def test_no_funding_or_no_strategy_approval_never_submits():
    db, cfg, broker, signal = setup()
    broker.adapter.get_buying_power.return_value = 0
    assert call(db, cfg, broker, signal).reason == "account_unfunded_or_invalid"
    db.query(RobinhoodStrategyReadiness).one().enabled = False
    db.commit()
    assert call(db, cfg, broker, signal).reason == "robinhood_strategy_not_enabled"
    broker.submit_equity.assert_not_called()
    db.close()


def test_timeout_recovers_by_broker_ref_without_resubmitting():
    db, cfg, broker, signal = setup()
    broker.submit_equity.side_effect = TimeoutError("unknown outcome")
    result = call(db, cfg, broker, signal)
    assert result.status == "unknown"
    intent = db.query(OrderIntent).one()
    assert intent.broker_order_id is None
    broker.find_order_by_ref.return_value = {"id": "entry-recovered"}
    recovered = recover_uncertain_entry(db, broker, intent.intent_key)
    assert recovered.order_id == "entry-recovered"
    assert db.get(RobinhoodTradeLifecycle, result.trade_id).entry_order_id == "entry-recovered"
    broker.submit_equity.assert_called_once()
    db.close()


def test_crypto_uses_its_own_approval_and_buying_power():
    db, cfg, broker, signal = setup("crypto")
    broker.adapter.get_crypto_buying_power.return_value = 0
    assert call(db, cfg, broker, signal, "crypto").reason == "account_unfunded_or_invalid"
    broker.adapter.get_crypto_buying_power.return_value = 100
    result = call(db, cfg, broker, signal, "crypto")
    assert result.status == "submitted"
    broker.submit_crypto.assert_called_once()
    broker.submit_equity.assert_not_called()
    assert db.get(RobinhoodTradeLifecycle, result.trade_id).asset_class == "crypto"
    db.close()
