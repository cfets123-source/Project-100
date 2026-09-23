from uuid import uuid4

import pytest

from app.brokers.robinhood_adapter import RobinhoodMcpReadOnlyAdapter
from app.brokers.robinhood_execution import RobinhoodOrderTransport
from app.brokers.robinhood_mcp import RobinhoodMcpError


def transport(monkeypatch, **flags):
    adapter = RobinhoodMcpReadOnlyAdapter("test-token", "equity-6395", "crypto-6395")
    calls = []

    def tool(name, args=None):
        calls.append((name, args))
        if name == "get_equity_orders":
            return {"orders": [{"id": "owned", "account_number": "equity-6395"}]}
        if name == "get_crypto_orders":
            return {"results": [{"id": "owned", "rhs_account_number": "crypto-6395"}]}
        return {"id": "broker-order", "state": "queued"}

    monkeypatch.setattr(adapter, "_tool", tool)
    return RobinhoodOrderTransport(adapter, **flags), calls


def test_default_off_previews_without_mutating(monkeypatch):
    client, calls = transport(monkeypatch)
    client.preview_equity(symbol="SPY", side="buy", quantity="0.1")
    client.preview_crypto(symbol="BTC-USD", side="buy", quantity="0.001")
    assert calls[0][0] == "review_equity_order"
    assert calls[0][1]["account_number"] == "equity-6395"
    assert calls[1][0] == "preview_crypto_order"
    assert calls[1][1]["rhs_account_number"] == "crypto-6395"
    with pytest.raises(RobinhoodMcpError, match="disabled"):
        client.submit_equity(ref_id=str(uuid4()), symbol="SPY", side="buy", quantity="1")
    with pytest.raises(RobinhoodMcpError, match="disabled"):
        client.submit_crypto(ref_id=str(uuid4()), symbol="BTCUSD", side="buy", quantity="0.001")
    assert len(calls) == 2


def test_enabled_transport_uses_stable_uuid_and_correct_account(monkeypatch):
    client, calls = transport(monkeypatch, allow_equity=True, allow_crypto=True)
    ref = str(uuid4())
    client.submit_equity(ref_id=ref, symbol="SPY", side="sell", quantity="1")
    client.submit_crypto(ref_id=ref, symbol="ETHUSD", side="sell", quantity="0.01")
    assert calls[0] == ("place_equity_order", {
        "account_number": "equity-6395", "symbol": "SPY", "side": "sell",
        "type": "market", "quantity": "1", "time_in_force": "gfd",
        "market_hours": "regular_hours", "ref_id": ref})
    assert calls[1][0] == "place_crypto_order"
    assert calls[1][1]["rhs_account_number"] == "crypto-6395"
    assert calls[1][1]["ref_id"] == ref


def test_invalid_orders_and_cancel_ownership_fail_closed(monkeypatch):
    client, calls = transport(monkeypatch, allow_equity=True, allow_crypto=True)
    with pytest.raises(RobinhoodMcpError, match="durable UUID"):
        client.submit_equity(ref_id="not-a-uuid", symbol="SPY", side="buy", quantity="1")
    with pytest.raises(RobinhoodMcpError, match="Fractional"):
        client.preview_equity(symbol="SPY", side="buy", quantity="0.5",
                              order_type="limit", limit_price="100")
    with pytest.raises(RobinhoodMcpError, match="Invalid quantity"):
        client.preview_crypto(symbol="BTCUSD", side="buy", quantity="NaN")
    with pytest.raises(RobinhoodMcpError, match="ownership"):
        client.cancel_crypto("other")
    assert all(name not in {"place_equity_order", "place_crypto_order", "cancel_crypto_order"}
               for name, _ in calls)


def test_factory_requires_live_and_separate_broker_gates(monkeypatch):
    from app.brokers.robinhood_execution import load_agentic_order_transport
    from app.core.config import Settings, TradingMode, AutonomyLevel

    adapter = RobinhoodMcpReadOnlyAdapter("token", "equity-6395", "crypto-6395")
    monkeypatch.setattr("app.brokers.robinhood_adapter.load_agentic_read_only_adapter",
                        lambda db, key: (adapter, {"account_id": "equity-6395"}))
    cfg = Settings(TRADING_MODE=TradingMode.LIVE,
                   AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS,
                   LIVE_TRADING_ENABLED=True,
                   ROBINHOOD_EQUITY_EXECUTION_ENABLED=True,
                   ROBINHOOD_CRYPTO_EXECUTION_ENABLED=False)
    client = load_agentic_order_transport(object(), "key", cfg)
    assert client.allow_equity is True
    assert client.allow_crypto is False
    cfg.LIVE_TRADING_ENABLED = False
    assert load_agentic_order_transport(object(), "key", cfg).allow_equity is False
