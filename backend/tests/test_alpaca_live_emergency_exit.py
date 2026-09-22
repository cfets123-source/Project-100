from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.models import SystemStateRecord
from app.runtime import alpaca_live_emergency_exit as emergency


def database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(SystemStateRecord(id="current", state="halted", reason="missing stop"))
    db.commit()
    return db


def test_halted_uncovered_position_sends_one_exact_sell(monkeypatch):
    db = database()
    reader = SimpleNamespace(paper=False, headers={"APCA-API-KEY-ID": "key",
                                                   "APCA-API-SECRET-KEY": "secret"},
                             get_positions=lambda: [{"symbol": "ORCL", "qty": "0.223500044"}],
                             get_orders=lambda: [])
    submitted = []
    class Writer:
        def __init__(self, *args, **kwargs):
            assert kwargs == {"paper": False, "allow_order_submission": True}
        def place_order(self, order):
            submitted.append(order)
            return SimpleNamespace(order_id="exit-1", status="accepted", filled_qty=0)
    monkeypatch.setattr(emergency, "load_read_only_adapter", lambda *args, **kwargs: (reader, False))
    monkeypatch.setattr(emergency, "AlpacaBrokerAdapter", Writer)
    result = emergency.emergency_exit(db, SimpleNamespace(BROKER_TOKEN_ENCRYPTION_KEY="unused"), "ORCL")
    assert len(submitted) == 1
    assert submitted[0].side == "sell" and submitted[0].quantity == 0.223500044
    assert submitted[0].time_in_force == "day"
    assert result["filled"] is False


def test_existing_exit_prevents_duplicate_order(monkeypatch):
    db = database()
    reader = SimpleNamespace(paper=False, headers={},
                             get_positions=lambda: [{"symbol": "ORCL", "qty": "0.223500044"}],
                             get_orders=lambda: [{"symbol": "ORCL", "side": "sell", "status": "accepted"}])
    monkeypatch.setattr(emergency, "load_read_only_adapter", lambda *args, **kwargs: (reader, False))
    with pytest.raises(RuntimeError, match="active sell order already exists"):
        emergency.emergency_exit(db, SimpleNamespace(BROKER_TOKEN_ENCRYPTION_KEY="unused"), "ORCL")


def test_emergency_path_refuses_when_system_is_not_halted(monkeypatch):
    db = database()
    db.get(SystemStateRecord, "current").state = "live"
    db.commit()
    monkeypatch.setattr(emergency, "load_read_only_adapter",
                        lambda *args, **kwargs: pytest.fail("broker must not be reached"))
    with pytest.raises(RuntimeError, match="requires halted state"):
        emergency.emergency_exit(db, SimpleNamespace(BROKER_TOKEN_ENCRYPTION_KEY="unused"), "ORCL")
