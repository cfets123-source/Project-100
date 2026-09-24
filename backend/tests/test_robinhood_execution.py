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
        if name == "get_accounts":
            return {"accounts": [{"account_number": "equity-6395", "agentic_allowed": True,
                                  "state": "active", "option_level": "option_level_2"}]}
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


def test_level_two_option_review_builds_single_leg_limit_without_order(monkeypatch):
    client, calls = transport(monkeypatch)
    option_id = str(uuid4())
    contract = {"id": option_id, "chain_symbol": "SPY", "underlying_type": "equity",
                "state": "active", "tradability": "tradable"}
    client.preview_long_option(contract=contract, quantity=1, side="buy", limit_price="0.29")
    assert calls[-1] == ("review_option_order", {
        "account_number": "equity-6395", "chain_symbol": "SPY", "underlying_type": "equity",
        "legs": [{"option_id": option_id, "side": "buy", "position_effect": "open"}],
        "quantity": "1", "type": "limit", "price": "0.29",
        "time_in_force": "gfd", "market_hours": "regular_hours"})
    assert all(name != "place_option_order" for name, _ in calls)


def test_option_review_rejects_fractional_and_unapproved_accounts(monkeypatch):
    client, calls = transport(monkeypatch)
    contract = {"id": str(uuid4()), "chain_symbol": "SPY", "underlying_type": "equity",
                "state": "active", "tradability": "tradable"}
    with pytest.raises(RobinhoodMcpError, match="whole contracts"):
        client.preview_long_option(contract=contract, quantity="0.5", side="buy", limit_price="0.29")
    monkeypatch.setattr(client.adapter, "_tool", lambda name, args=None: {
        "accounts": [{"account_number": "equity-6395", "agentic_allowed": True,
                      "state": "active", "option_level": "option_level_0"}]})
    with pytest.raises(RobinhoodMcpError, match="not approved"):
        client.preview_long_option(contract=contract, quantity=1, side="buy", limit_price="0.29")
    assert all(name != "place_option_order" for name, _ in calls)


def test_option_reads_bind_exact_account_order_and_contract(monkeypatch):
    client, calls = transport(monkeypatch)
    option_id, order_id = str(uuid4()), str(uuid4())
    order = {"id": order_id, "state": "confirmed", "legs": [
        {"option_id": option_id, "side": "sell", "position_effect": "close"}]}
    def tool(name, args=None):
        calls.append((name, args))
        if name == "get_option_orders":
            return {"orders": [order], "next": None}
        if name == "get_option_positions":
            return {"positions": [{"option_id": option_id, "quantity": "1"}], "next": None}
        raise AssertionError(name)
    monkeypatch.setattr(client.adapter, "_tool", tool)
    assert client.get_option_order(order_id, option_id) == order
    assert client.get_option_position(option_id)["quantity"] == "1"
    assert client.active_option_exit_orders(option_id) == [order]
    assert all(args["account_number"] == "equity-6395" for _, args in calls)
    assert all(name not in {"place_option_order", "cancel_option_order"} for name, _ in calls)


def test_option_reads_fail_closed_on_mismatch_or_incomplete_history(monkeypatch):
    client, _ = transport(monkeypatch)
    option_id, other_id, order_id = str(uuid4()), str(uuid4()), str(uuid4())
    monkeypatch.setattr(client.adapter, "_tool", lambda name, args=None: {
        "orders": [{"id": order_id, "legs": [{"option_id": other_id}]}], "next": None})
    with pytest.raises(RobinhoodMcpError, match="contract mismatch"):
        client.get_option_order(order_id, option_id)
    monkeypatch.setattr(client.adapter, "_tool", lambda name, args=None: {
        "orders": [], "next": "more"})
    with pytest.raises(RobinhoodMcpError, match="incomplete"):
        client.active_option_exit_orders(option_id)
    monkeypatch.setattr(client.adapter, "_tool", lambda name, args=None: {
        "positions": [{"option_id": other_id, "quantity": "1"}], "next": None})
    with pytest.raises(RobinhoodMcpError, match="contract mismatch"):
        client.get_option_position(option_id)


def test_option_submission_mapping_has_separate_default_off_gate(monkeypatch):
    contract = {"id": str(uuid4()), "chain_symbol": "SPY", "underlying_type": "equity",
                "state": "active", "tradability": "tradable"}
    order = {"contract": contract, "quantity": 1, "side": "buy", "limit_price": "0.29"}
    client, calls = transport(monkeypatch, allow_equity=True)
    with pytest.raises(RobinhoodMcpError, match="options execution is disabled"):
        client.submit_long_option(ref_id=str(uuid4()), **order)
    assert not calls
    client, calls = transport(monkeypatch, allow_options=True)
    ref = str(uuid4())
    client.submit_long_option(ref_id=ref, **order)
    assert calls[-1] == ("place_option_order", {
        "account_number": "equity-6395", "legs": [{"option_id": contract["id"],
        "side": "buy", "position_effect": "open"}], "quantity": "1", "type": "limit",
        "price": "0.29", "time_in_force": "gfd", "market_hours": "regular_hours", "ref_id": ref})


def test_option_stop_requires_exact_long_position_and_no_active_exit(monkeypatch):
    client, calls = transport(monkeypatch, allow_options=True)
    option_id = str(uuid4())
    contract = {"id": option_id, "chain_symbol": "SPY", "underlying_type": "equity",
                "state": "active", "tradability": "tradable"}
    position = {"option_id": option_id, "type": "long", "quantity": "1"}
    exits = []
    original_tool = client.adapter._tool

    def tool(name, args=None):
        if name == "get_option_positions":
            return {"positions": [position], "next": None}
        if name == "get_option_orders":
            return {"orders": exits, "next": None}
        return original_tool(name, args)

    monkeypatch.setattr(client.adapter, "_tool", tool)
    client.preview_option_stop(contract=contract, quantity=1, stop_price="0.20")
    assert calls[-1] == ("review_option_order", {
        "account_number": "equity-6395", "chain_symbol": "SPY", "underlying_type": "equity",
        "legs": [{"option_id": option_id, "side": "sell", "position_effect": "close"}],
        "quantity": "1", "type": "stop_market", "stop_price": "0.20",
        "time_in_force": "gfd", "market_hours": "regular_hours"})
    with pytest.raises(RobinhoodMcpError, match="quantity"):
        client.preview_option_stop(contract=contract, quantity=2, stop_price="0.20")
    exits.append({"id": str(uuid4()), "state": "confirmed", "legs": [
        {"option_id": option_id, "side": "sell", "position_effect": "close"}]})
    with pytest.raises(RobinhoodMcpError, match="active close order"):
        client.submit_option_stop(ref_id=str(uuid4()), contract=contract,
                                  quantity=1, stop_price="0.20")
    assert all(name != "place_option_order" for name, _ in calls)


def test_option_stop_submission_and_ref_recovery_are_account_bound(monkeypatch):
    client, calls = transport(monkeypatch, allow_options=True)
    option_id, ref = str(uuid4()), str(uuid4())
    contract = {"id": option_id, "chain_symbol": "SPY", "underlying_type": "equity",
                "state": "active", "tradability": "tradable"}
    original_tool = client.adapter._tool

    def tool(name, args=None):
        if name == "get_option_positions":
            return {"positions": [{"option_id": option_id, "type": "long",
                                    "quantity": "1"}], "next": None}
        if name == "get_option_orders":
            return {"orders": [], "next": None}
        return original_tool(name, args)

    monkeypatch.setattr(client.adapter, "_tool", tool)
    client.submit_option_stop(ref_id=ref, contract=contract, quantity=1,
                              stop_price="0.20")
    assert calls[-1] == ("place_option_order", {
        "account_number": "equity-6395",
        "legs": [{"option_id": option_id, "side": "sell", "position_effect": "close"}],
        "quantity": "1", "type": "stop_market", "stop_price": "0.20",
        "time_in_force": "gfd", "market_hours": "regular_hours", "ref_id": ref})
    assert client.find_order_by_ref("option", ref) is None


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


def test_stop_orders_are_gtc_and_require_a_trigger(monkeypatch):
    client, calls = transport(monkeypatch, allow_equity=True, allow_crypto=True)
    ref = str(uuid4())
    client.preview_equity(symbol="F", side="sell", quantity="1",
                          order_type="stop_market", stop_price="10")
    client.submit_crypto(ref_id=ref, symbol="BTCUSD", side="sell", quantity="0.001",
                         order_type="stop_loss", stop_price="100000")
    assert calls[0][1]["type"] == "stop_market"
    assert calls[0][1]["time_in_force"] == "gtc"
    assert calls[0][1]["stop_price"] == "10"
    assert calls[1][1]["type"] == "stop_loss"
    assert calls[1][1]["time_in_force"] == "gtc"
    with pytest.raises(RobinhoodMcpError, match="Invalid stop price"):
        client.preview_crypto(symbol="BTCUSD", side="sell", quantity="0.001",
                              order_type="stop_loss")
    with pytest.raises(RobinhoodMcpError, match="Fractional"):
        client.preview_equity(symbol="F", side="sell", quantity="0.5",
                              order_type="stop_market", stop_price="10")


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
    assert client.allow_options is False
    cfg.ROBINHOOD_OPTIONS_EXECUTION_ENABLED = True
    assert load_agentic_order_transport(object(), "key", cfg).allow_options is False
    cfg.ALLOW_OPTIONS = True
    assert load_agentic_order_transport(object(), "key", cfg).allow_options is True
    cfg.LIVE_TRADING_ENABLED = False
    assert load_agentic_order_transport(object(), "key", cfg).allow_equity is False
    assert load_agentic_order_transport(object(), "key", cfg).allow_options is False


def test_emergency_sell_scan_requires_broker_order_list(monkeypatch):
    client, calls = transport(monkeypatch)
    assert client.active_sell_orders("equity", "F") == []
    assert calls[-1] == ("get_equity_orders", {"account_number": "equity-6395"})
    monkeypatch.setattr(client.adapter, "_tool", lambda name, args: {"orders": None})
    with pytest.raises(RobinhoodMcpError, match="order history"):
        client.active_sell_orders("equity", "F")
    monkeypatch.setattr(client.adapter, "_tool", lambda name, args: {"orders": [
        {"id": "unclear", "symbol": "F", "side": "sell", "state": "new_broker_state"},
        {"id": "done", "symbol": "F", "side": "sell", "state": "filled"}]})
    assert [row["id"] for row in client.active_sell_orders("equity", "F")] == ["unclear"]
