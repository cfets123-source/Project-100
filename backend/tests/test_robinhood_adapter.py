from app.brokers.robinhood_adapter import RobinhoodMcpReadOnlyAdapter
from app.brokers.robinhood_mcp import RobinhoodMcpError


def adapter(monkeypatch):
    a = RobinhoodMcpReadOnlyAdapter('token', 'agentic-1')
    data = {
        'get_accounts': {'accounts': [{'account_number': 'agentic-1', 'agentic_allowed': True, 'type': 'limited_margin'}]},
        'get_portfolio': {'cash': '100.00', 'total_value': '100.00', 'buying_power': {'buying_power': '100.00'}},
        'get_equity_positions': {'positions': []},
        'get_equity_orders': {'orders': []},
        'get_equity_quotes': {'results': [{'quote': {'symbol': 'TST', 'bid_price': '9.99', 'ask_price': '10.01', 'last_trade_price': '10.00', 'venue_last_trade_time': '2025-01-01T15:00:00Z'}}]},
    }
    monkeypatch.setattr(a, '_tool', lambda name, arguments=None: data[name])
    return a


def test_read_only_adapter_maps_verified_broker_reads(monkeypatch):
    a = adapter(monkeypatch)
    assert a.authenticate()
    assert a.get_accounts()[0]['account_id'] == 'agentic-1'
    assert a.get_balances() == {'cash': 100.0, 'equity': 100.0}
    assert a.get_buying_power() == 100.0
    assert a.get_positions() == []
    assert a.get_orders() == []
    assert a.get_quotes(['TST'])[0].symbol == 'TST'


def test_read_only_adapter_refuses_order_mutation(monkeypatch):
    a = adapter(monkeypatch)
    try:
        a.place_order(None)
    except RobinhoodMcpError as exc:
        assert 'disabled' in str(exc)
    else:
        raise AssertionError('read-only adapter accepted a live order')
