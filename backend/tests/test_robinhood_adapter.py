from app.brokers.robinhood_adapter import RobinhoodMcpReadOnlyAdapter
from app.brokers.robinhood_mcp import RobinhoodMcpError
from datetime import datetime, timezone


def adapter(monkeypatch):
    a = RobinhoodMcpReadOnlyAdapter('token', 'agentic-1', 'crypto-1')
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


def test_readiness_selects_only_active_agentic_account(monkeypatch):
    import app.brokers.robinhood_adapter as module

    class Stub:
        def __init__(self, token, designated_account_id):
            self.designated_account_id = designated_account_id
        def get_accounts(self):
            return [
                {'account_id': 'ordinary', 'agentic_allowed': False, 'state': 'active'},
                {'account_id': 'agentic', 'agentic_allowed': True, 'state': 'active', 'type': 'limited_margin'},
            ]
        def authenticate(self): return True
        def get_balances(self): return {'cash': 100.0, 'equity': 100.0}
        def get_buying_power(self): return 100.0
        def get_positions(self): return []
        def get_orders(self): return []

    monkeypatch.setattr('app.brokers.robinhood_mcp._access_token', lambda db, key: 'token')
    monkeypatch.setattr(module, 'RobinhoodMcpReadOnlyAdapter', Stub)
    result = module.verify_agentic_readiness(object(), 'key')
    assert result['read_only_ready'] is True
    assert result['execution_enabled'] is False
    assert result['expected_account_id'] == 'agentic'


def test_crypto_quotes_reject_crossed_or_stale_markets(monkeypatch):
    a = adapter(monkeypatch)
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {'symbol': 'BTCUSD', 'bid_price': '100', 'ask_price': '99', 'mark_price': '99.5', 'updated_at': now},
        {'symbol': 'ETHUSD', 'bid_price': '200', 'ask_price': '201', 'mark_price': '200.5', 'updated_at': now},
    ]
    monkeypatch.setattr(a, '_tool', lambda name, arguments=None: {'results': rows})
    quotes = a.get_crypto_quotes(['BTC-USD', 'ETH-USD'])
    assert quotes[0]['valid_for_execution'] is False
    assert quotes[0]['quality_reason'] == 'crossed_market'
    assert quotes[1]['valid_for_execution'] is True
    assert quotes[1]['quality_reason'] == 'current'
    rows[1]['updated_at'] = '2025-01-01T00:00:00Z'
    assert a.get_crypto_quotes(['BTC-USD', 'ETH-USD'])[1]['valid_for_execution'] is False
    assert a.get_crypto_quotes(['BTC-USD', 'ETH-USD'])[1]['quality_reason'] == 'stale_quote'


def test_crypto_reads_use_only_designated_agentic_account(monkeypatch):
    a = adapter(monkeypatch)
    calls = []
    def tool(name, arguments=None):
        calls.append((name, arguments))
        return {'results': []}
    monkeypatch.setattr(a, '_tool', tool)
    assert a.get_crypto_positions() == []
    assert a.get_crypto_orders() == []
    assert all(arguments['rhs_account_number'] == 'crypto-1' for _, arguments in calls)
