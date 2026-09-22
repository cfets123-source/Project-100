from datetime import datetime, timezone

import pytest

from app.brokers.alpaca_adapter import AlpacaBrokerAdapter, AlpacaBrokerError
from app.brokers.base import OrderRequest


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class RateLimitedResponse(Response):
    def __init__(self, payload, *, status_code=200, headers=None):
        super().__init__(payload)
        self.status_code = status_code
        self.headers = headers or {}


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


def test_day_bracket_submission_keeps_whole_quantity_and_both_exit_legs():
    client = Client()
    adapter = AlpacaBrokerAdapter('key', 'secret', allow_order_submission=True, client=client)
    adapter.place_order(OrderRequest(symbol='LCID', side='buy', quantity=1,
                                     order_class='bracket', take_profit_price=5.0,
                                     stop_loss_price=4.0, time_in_force='day'))
    assert client.calls[-1][2]['json'] == {
        'symbol': 'LCID', 'side': 'buy', 'qty': '1', 'type': 'market', 'time_in_force': 'day',
        'order_class': 'bracket', 'take_profit': {'limit_price': '5.0'},
        'stop_loss': {'stop_price': '4.0'},
    }


def test_fractional_bracket_is_rejected_locally_without_a_broker_request():
    client = Client()
    adapter = AlpacaBrokerAdapter('key', 'secret', allow_order_submission=True, client=client)
    with pytest.raises(AlpacaBrokerError, match='fractional orders must be simple'):
        adapter.place_order(OrderRequest(symbol='LCID', side='buy', quantity=0.1,
                                         order_class='bracket', take_profit_price=5.0,
                                         stop_loss_price=4.0, time_in_force='day'))
    assert client.calls == []


def test_orders_request_includes_nested_bracket_legs():
    client = Client()
    adapter = AlpacaBrokerAdapter('key', 'secret', client=client)
    adapter.get_orders()
    assert client.calls[-1][2]['params'] == {'status': 'all', 'limit': 500, 'nested': 'true'}


def test_asset_catalog_is_read_only_and_filters_to_tradable_symbols():
    class CatalogClient(Client):
        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if url.endswith('/v2/assets'):
                return Response([
                    {'id': 'a', 'symbol': 'AAPL', 'name': 'Apple', 'asset_class': 'us_equity',
                     'exchange': 'NASDAQ', 'tradable': True, 'fractionable': True, 'shortable': True},
                    {'id': 'b', 'symbol': 'OLD', 'tradable': False},
                ])
            return super().request(method, url, **kwargs)
    client = CatalogClient()
    assets = AlpacaBrokerAdapter('key', 'secret', client=client).list_active_assets()
    assert assets == [{'id': 'a', 'symbol': 'AAPL', 'name': 'Apple', 'asset_class': 'us_equity',
                       'exchange': 'NASDAQ', 'tradable': True, 'fractionable': True, 'shortable': True}]
    assert client.calls[-1][0] == 'GET'
    assert client.calls[-1][2]['params'] == {'status': 'active', 'asset_class': 'us_equity'}


def test_stop_submission_uses_alpaca_stop_price_and_gtc():
    client = Client()
    adapter = AlpacaBrokerAdapter('key', 'secret', allow_order_submission=True, client=client)
    adapter.place_order(OrderRequest(symbol='AAPL', side='sell', quantity=1,
                                     order_type='stop', stop_price=90, time_in_force='gtc'))
    assert client.calls[-1][2]['json'] == {'symbol': 'AAPL', 'side': 'sell', 'qty': '1',
                                            'type': 'stop', 'time_in_force': 'gtc', 'stop_price': '90'}


def test_cancel_accepts_alpaca_empty_success_response():
    client = Client()
    adapter = AlpacaBrokerAdapter('key', 'secret', allow_order_submission=True, client=client)
    assert adapter.cancel_order('order-1')
    method, url, _ = client.calls[-1]
    assert method == 'DELETE'
    assert url.endswith('/v2/orders/order-1')


def test_get_honors_rate_limit_reset_before_retrying(monkeypatch):
    class ThrottledClient:
        def __init__(self): self.calls = 0
        def request(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return RateLimitedResponse({}, status_code=429, headers={
                    'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '105',
                })
            return RateLimitedResponse({'id': 'acct', 'status': 'ACTIVE'})
    sleeps = []
    monkeypatch.setattr('app.brokers.alpaca_adapter.time.time', lambda: 100.0)
    monkeypatch.setattr('app.brokers.alpaca_adapter.time.sleep', sleeps.append)
    client = ThrottledClient()
    adapter = AlpacaBrokerAdapter('key', 'secret', client=client)
    assert adapter.authenticate() is True
    assert client.calls == 2
    assert sleeps == [5.1]
