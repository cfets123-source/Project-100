from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

from app.core.config import Settings, TradingMode, AutonomyLevel
from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import (OrderIntent, RiskReservation, RobinhoodOptionLifecycle,
                               RobinhoodTradeLifecycle,
                               SystemStateRecord, TradeDecisionRecord)
from app.runtime.robinhood_lifecycle_worker import run_cycle


def test_default_off_worker_does_not_touch_broker(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr("app.runtime.robinhood_lifecycle_worker.load_agentic_order_transport",
                        lambda *_: (_ for _ in ()).throw(AssertionError("broker touched")))
    assert run_cycle(db, Settings()) == {"status": "disabled", "processed": 0}
    db.close()


def test_enabled_worker_with_no_recorded_entry_remains_idle(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr("app.runtime.robinhood_lifecycle_worker.load_agentic_order_transport",
                        lambda *_: (_ for _ in ()).throw(AssertionError("broker touched")))
    cfg = Settings(TRADING_MODE=TradingMode.LIVE,
                   AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS,
                   LIVE_TRADING_ENABLED=True, ROBINHOOD_CRYPTO_EXECUTION_ENABLED=True)
    assert run_cycle(db, cfg) == {"status": "idle", "processed": 0}
    db.close()


def test_stale_preparing_intent_releases_only_its_reservation(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    trade = TradeDecisionRecord(symbol="F", asset_class="equity",
                                strategy="robinhood-equity-test", status="open")
    db.add(trade)
    db.commit()
    db.add(OrderIntent(intent_key="old", decision_id="d1", trade_id=trade.trade_id,
                       account_id="agentic", symbol="F", status="preparing",
                       created_at=datetime.utcnow() - timedelta(minutes=3)))
    db.add(RiskReservation(id="r1", account_id="agentic", decision_id="d1",
                           risk_dollars=1, notional=10, status="active"))
    db.commit()
    monkeypatch.setattr("app.runtime.robinhood_lifecycle_worker.load_agentic_order_transport",
                        lambda *_: (_ for _ in ()).throw(AssertionError("broker touched")))
    cfg = Settings(TRADING_MODE=TradingMode.LIVE,
                   AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS,
                   LIVE_TRADING_ENABLED=True, ROBINHOOD_EQUITY_EXECUTION_ENABLED=True)
    assert run_cycle(db, cfg)["status"] == "idle"
    assert db.get(OrderIntent, "old").status == "canceled"
    assert db.get(RiskReservation, "r1").status == "released"
    db.close()


def test_pending_emergency_exit_halts_new_entries_but_keeps_lifecycle_running(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(RobinhoodTradeLifecycle(trade_id="t1", account_id="agentic", asset_class="equity",
                                   symbol="F", quantity=1, stop_price=9, entry_order_id="entry-1",
                                   stop_ref_id="11111111-1111-1111-1111-111111111111",
                                   status="emergency_pending"))
    db.commit()
    monkeypatch.setattr("app.runtime.robinhood_lifecycle_worker.load_agentic_order_transport",
                        lambda *_: object())
    monkeypatch.setattr("app.runtime.robinhood_lifecycle_worker.reconcile_trade",
                        lambda *_: {"status": "emergency_pending", "reason": "stop_preview_rejected",
                                    "trade_id": "t1"})
    cfg = Settings(TRADING_MODE=TradingMode.LIVE,
                   AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS,
                   LIVE_TRADING_ENABLED=True, ROBINHOOD_EQUITY_EXECUTION_ENABLED=True)
    assert run_cycle(db, cfg)["outcomes"][0]["status"] == "emergency_pending"
    assert db.get(SystemStateRecord, "current").state == "halted"
    db.close()


def test_option_worker_is_read_only_and_halts_on_unprotected_fill(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(RobinhoodOptionLifecycle(trade_id="option-trade", account_id="agentic",
                                   option_id="option-contract", underlying_symbol="SPY",
                                   quantity=1, multiplier=100, entry_order_id="entry-option",
                                   status="entry_pending"))
    db.commit()
    transport = object()
    monkeypatch.setattr("app.runtime.robinhood_lifecycle_worker.load_agentic_order_transport",
                        lambda *_: transport)
    calls = []
    def reconcile(_db, seen_transport, trade_id):
        calls.append((seen_transport, trade_id))
        return {"status": "safety_failure", "reason": "option_fill_without_stop",
                "trade_id": trade_id}
    monkeypatch.setattr("app.runtime.robinhood_lifecycle_worker.reconcile_option_trade", reconcile)
    cfg = Settings(TRADING_MODE=TradingMode.LIVE,
                   AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS,
                   LIVE_TRADING_ENABLED=True, ROBINHOOD_OPTIONS_EXECUTION_ENABLED=True)
    result = run_cycle(db, cfg)
    assert result["outcomes"][0]["reason"] == "option_fill_without_stop"
    assert calls == [(transport, "option-trade")]
    assert db.get(SystemStateRecord, "current").state == "halted"
    db.close()


def test_option_submitted_without_lifecycle_halts_without_broker_call(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    trade = TradeDecisionRecord(symbol="SPY", asset_class="option",
                                strategy="robinhood-option-test", status="open")
    db.add(trade)
    db.commit()
    db.add(OrderIntent(intent_key="option-orphan", decision_id="option-decision",
                       trade_id=trade.trade_id, account_id="agentic", symbol="SPY",
                       side="buy", quantity=1, status="submitted",
                       broker_order_id="option-entry"))
    db.commit()
    monkeypatch.setattr("app.runtime.robinhood_lifecycle_worker.load_agentic_order_transport",
                        lambda *_: (_ for _ in ()).throw(AssertionError("broker touched")))
    cfg = Settings(TRADING_MODE=TradingMode.LIVE,
                   AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS,
                   LIVE_TRADING_ENABLED=True, ROBINHOOD_OPTIONS_EXECUTION_ENABLED=True)
    result = run_cycle(db, cfg)
    assert result["outcomes"][0]["reason"] == "option_entry_lifecycle_missing"
    assert db.get(SystemStateRecord, "current").state == "halted"
    db.close()
