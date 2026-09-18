from datetime import datetime, timezone

from app.brokers.base import Quote
from app.market_data.alpaca import AlpacaMarketDataProvider
from app.market_data.base import validate_quote


class StubAdapter:
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).timestamp()
        self.balances_calls = self.positions_calls = 0

    def get_quotes(self, symbols):
        assert symbols == ["AAPL"]
        return [Quote("alpaca", "AAPL", self.timestamp, 0, 100.0, 100.2, 100.1, "open")]

    def get_balances(self):
        self.balances_calls += 1
        return {"cash": 100, "equity": 100, "buying_power": 100}

    def get_positions(self):
        self.positions_calls += 1
        return []


def test_alpaca_provider_uses_source_timestamp_and_receipt_time():
    provider = AlpacaMarketDataProvider(StubAdapter(), entitlement="real_time")
    quote = provider.get_quote("AAPL")
    assert quote.source == "alpaca"
    assert quote.entitlement == "real_time"
    assert validate_quote(quote, 5).valid


def test_account_snapshot_is_stale_until_explicitly_refreshed():
    adapter = StubAdapter()
    provider = AlpacaMarketDataProvider(adapter)
    assert provider.get_account_snapshot_age_seconds() == float("inf")
    snapshot = provider.refresh_account_snapshot()
    assert snapshot["balances"]["cash"] == 100
    assert provider.get_account_snapshot_age_seconds() < 1
    assert adapter.balances_calls == adapter.positions_calls == 1


def test_missing_symbol_is_not_invented():
    provider = AlpacaMarketDataProvider(StubAdapter())
    assert provider.get_quote("MSFT") is None
