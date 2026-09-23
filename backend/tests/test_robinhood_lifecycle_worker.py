from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, TradingMode, AutonomyLevel
from app.db.session import Base
from app.models import models  # noqa: F401
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
