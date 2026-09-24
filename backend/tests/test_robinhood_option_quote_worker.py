from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.robinhood_adapter import RobinhoodMcpReadOnlyAdapter
from app.brokers.robinhood_mcp import RobinhoodMcpError
from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import RobinhoodOptionQuoteObservation
from app.runtime.robinhood_option_quote_worker import collect_once


def test_quote_collector_records_exact_bid_ask_once_without_order_call():
    option_id = str(uuid4())
    contract = {"id": option_id, "chain_symbol": "SPY", "expiration_date": "2026-10-02",
                "strike_price": "785.0000", "type": "call", "trade_value_multiplier": "100",
                "state": "active", "tradability": "tradable"}
    quote = {"instrument_id": option_id, "symbol": "SPY", "expiration": "2026-10-02",
             "strike": "785.0000", "type": "call", "multiplier": 100,
             "bid": .46, "ask": .47, "bid_size": 349, "ask_size": 430,
             "volume": 613, "open_interest": 59233, "quality_reason": "current",
             "as_of": datetime.now(timezone.utc).isoformat()}
    adapter = Mock()
    adapter.get_option_instruments_by_ids.return_value = [contract]
    adapter.get_option_quotes.return_value = [quote]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert collect_once(db, adapter, [option_id])["new_quotes"] == 1
        assert collect_once(db, adapter, [option_id])["new_quotes"] == 0
        rows = db.query(RobinhoodOptionQuoteObservation).all()
        assert len(rows) == 1
        assert (rows[0].bid, rows[0].ask, rows[0].ask_size) == (.46, .47, 430)
        assert rows[0].broker_as_of == quote["as_of"]
    assert not any("order" in call[0] for call in adapter.method_calls)


def test_quote_collector_rejects_contract_mismatch_without_recording():
    option_id = str(uuid4())
    adapter = Mock()
    adapter.get_option_instruments_by_ids.return_value = [{
        "id": option_id, "state": "active", "tradability": "tradable"}]
    adapter.get_option_quotes.return_value = [{"instrument_id": str(uuid4())}]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="mismatch"):
            collect_once(db, adapter, [option_id])
        assert db.query(RobinhoodOptionQuoteObservation).count() == 0


def test_contract_id_lookup_rejects_partial_pages(monkeypatch):
    option_id = str(uuid4())
    adapter = RobinhoodMcpReadOnlyAdapter("token", "agentic")
    calls = []
    def tool(name, args=None):
        calls.append((name, args))
        return {"instruments": [{"id": option_id}], "next": "more"}
    monkeypatch.setattr(adapter, "_tool", tool)
    with pytest.raises(RobinhoodMcpError, match="Incomplete"):
        adapter.get_option_instruments_by_ids([option_id])
    assert calls == [("get_option_instruments", {"ids": option_id})]
