from datetime import datetime, timezone

import pytest

from app.brokers.alpaca_adapter import AlpacaBrokerAdapter, AlpacaBrokerError
from app.brokers.base import OrderRequest


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class Client:
    def __init__(self): self.calls = []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith('/v2/account'):
            return Response({'id': 'acct', 'status': 'ACTIVE', 'equity': '100', 'cash': '100', 'buying_power': '100'})
        if 'quotes/latest' in url:
            return Response({'quotes': {'AAPL': {'bp': 10, 'ap': 11, 't': datetime.now(timezone.utc).isoformat()}}})
        if method == 'POST':
            return Response({'id': 'order-1', 'status': 'accepted', 'filled_qty': '0'})
        return Response([])


def test_read_only_account_and_quote_checks_use_paper_endpoint():
    client = Client()
    adapter = AlpacaBrokerAdapter('key', 'secret', client=client)
    assert adapter.authenticate()
    assert adapter.get_balances()['equity'] == 100
    quote = adapter.get_quotes(['AAPL'])[0]
    assert quote.symbol == 'AAPL' and quote.ask == 11
    assert all('paper-api.alpaca.markets' in url or 'data.alpaca.markets' in url for _, url, _ in client.calls)


def test_order_submission_is_hard_disabled_by_default():
    adapter = AlpacaBrokerAdapter('key', 'secret', client=Client())
    with pytest.raises(AlpacaBrokerError, match='disabled'):
        adapter.place_order(OrderRequest(symbol='AAPL', side='buy', quantity=1))


def test_enabled_submission_has_explicit_order_payload():
    client = Client()
    adapter = AlpacaBrokerAdapter('key', 'secret', allow_order_submission=True, client=client)
    result = adapter.place_order(OrderRequest(symbol='AAPL', side='buy', quantity=1))
    assert result.order_id == 'order-1'
    assert client.calls[-1][2]['json'] == {'symbol': 'AAPL', 'side': 'buy', 'qty': '1', 'type': 'market', 'time_in_force': 'day'}


def test_cancel_accepts_alpaca_empty_success_response():
    client = Client()
    adapter = AlpacaBrokerAdapter('key', 'secret', allow_order_submission=True, client=client)
    assert adapter.cancel_order('order-1')
    method, url, _ = client.calls[-1]
    assert method == 'DELETE'
    assert url.endswith('/v2/orders/order-1')
