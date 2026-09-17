import time
from app.market_data.base import MarketQuote, validate_quote
from app.market_data.simulated import SimulatedMarketDataProvider


def base_quote(**overrides):
    now = time.time()
    defaults = dict(source="t", symbol="TST", asset_class="equity", market_session="open",
                     source_timestamp=now, receipt_timestamp=now, bid=9.98, ask=10.02, last=10.0)
    defaults.update(overrides)
    return MarketQuote(**defaults)


def test_valid_quote_passes():
    v = validate_quote(base_quote(), max_age_seconds=5)
    assert v.valid


def test_missing_quote_rejected():
    v = validate_quote(None, max_age_seconds=5)
    assert not v.valid
    assert v.reason == "missing_quote"


def test_stale_quote_rejected():
    v = validate_quote(base_quote(source_timestamp=time.time() - 60), max_age_seconds=5)
    assert not v.valid
    assert v.reason == "stale_quote"


def test_future_dated_quote_rejected():
    v = validate_quote(base_quote(source_timestamp=time.time() + 60), max_age_seconds=5)
    assert not v.valid
    assert v.reason == "future_dated_quote"


def test_malformed_inverted_bid_ask_rejected():
    v = validate_quote(base_quote(bid=10.02, ask=9.98), max_age_seconds=5)
    assert not v.valid
    assert v.reason == "malformed_inverted_bid_ask"


def test_malformed_missing_fields_rejected():
    v = validate_quote(base_quote(bid=None), max_age_seconds=5)
    assert not v.valid
    assert v.reason == "malformed_missing_fields"


def test_out_of_order_timestamps_rejected():
    now = time.time()
    v = validate_quote(base_quote(source_timestamp=now, receipt_timestamp=now - 10), max_age_seconds=5)
    assert not v.valid
    assert v.reason == "out_of_order_timestamps"


def test_simulated_provider_fault_injection_stale():
    provider = SimulatedMarketDataProvider(prices={"TST": 10.0})
    provider.inject_fault("stale")
    q = provider.get_quote("TST")
    v = validate_quote(q, max_age_seconds=5)
    assert not v.valid
    assert v.reason == "stale_quote"


def test_simulated_provider_fault_injection_missing():
    provider = SimulatedMarketDataProvider(prices={"TST": 10.0})
    provider.inject_fault("missing")
    q = provider.get_quote("TST")
    assert q is None
