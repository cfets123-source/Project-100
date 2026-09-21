from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401
from app.runtime.alpaca_live_worker import allocated_live_equity, start_live_worker


def test_live_worker_refuses_startup_when_final_flag_is_off():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    cfg = SimpleNamespace(LIVE_TRADING_ENABLED=False)
    with pytest.raises(RuntimeError, match='live_trading_hard_disabled_in_config'):
        start_live_worker(db, cfg)


def test_live_equity_compounds_beyond_the_launch_baseline():
    cfg = SimpleNamespace(STARTING_CAPITAL=100.0)
    assert allocated_live_equity({"equity": 100.0}, cfg) == 100.0
    assert allocated_live_equity({"equity": 1_000.0}, cfg) == 1_000.0
