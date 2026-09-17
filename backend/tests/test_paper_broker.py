import time
import datetime as dt
import pytest
from unittest.mock import patch
from app.brokers.paper_broker import PaperBrokerAdapter
from app.brokers.base import Quote, OrderRequest


def quote_source(symbols):
    return [Quote(provider="test", symbol=s, timestamp=time.time(), age_seconds=0.1,
                   bid=9.98, ask=10.02, last=10.0, market_status="open") for s in symbols]


@pytest.fixture
def broker():
    return PaperBrokerAdapter(starting_cash=1000.0, quote_source=quote_source, slippage_bps=0)


def _during_market_hours():
    return dt.datetime(2025, 1, 6, 15, 0, 0)  # Monday 15:00 UTC


def test_buy_order_fills_and_updates_cash(broker):
    with patch("app.brokers.paper_broker.dt") as mock_dt:
        mock_dt.datetime.utcnow.return_value = _during_market_hours()
        result = broker.place_order(OrderRequest(symbol="TST", side="buy", quantity=10))
    assert result.status == "filled"
    assert broker.positions["TST"]["qty"] == 10
    assert broker.cash < 1000.0


def test_rejects_order_outside_market_hours(broker):
    with patch("app.brokers.paper_broker.dt") as mock_dt:
        mock_dt.datetime.utcnow.return_value = dt.datetime(2025, 1, 4, 15, 0, 0)  # Saturday
        result = broker.place_order(OrderRequest(symbol="TST", side="buy", quantity=10))
    assert result.status == "rejected"
    assert result.raw["reason"] == "market_closed"


def test_rejects_buy_when_insufficient_buying_power(broker):
    with patch("app.brokers.paper_broker.dt") as mock_dt:
        mock_dt.datetime.utcnow.return_value = _during_market_hours()
        result = broker.place_order(OrderRequest(symbol="TST", side="buy", quantity=10_000))
    assert result.status == "rejected"
    assert result.raw["reason"] == "insufficient_buying_power"


def test_rejects_sell_without_position(broker):
    with patch("app.brokers.paper_broker.dt") as mock_dt:
        mock_dt.datetime.utcnow.return_value = _during_market_hours()
        result = broker.place_order(OrderRequest(symbol="TST", side="sell", quantity=1))
    assert result.status == "rejected"
    assert result.raw["reason"] == "insufficient_position"


def test_sell_closes_position_and_returns_cash(broker):
    with patch("app.brokers.paper_broker.dt") as mock_dt:
        mock_dt.datetime.utcnow.return_value = _during_market_hours()
        broker.place_order(OrderRequest(symbol="TST", side="buy", quantity=10))
        cash_after_buy = broker.cash
        result = broker.place_order(OrderRequest(symbol="TST", side="sell", quantity=10))
    assert result.status == "filled"
    assert "TST" not in broker.positions
    assert broker.cash > cash_after_buy
