from fastapi.testclient import TestClient
import base64
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import app, live_decision_context, live_trades, terminal_market, terminal_ticker
from app.db.session import Base
from app.models.models import AuditLogEntry, StrategyValidationRecord, TradeDecisionRecord


def test_dashboard_is_read_only_and_identifies_operator_console():
    with TestClient(app) as client:
        page = client.get('/dashboard')
        assert page.status_code == 200
        assert 'Veloikos Trading' in page.text
        assert 'Open positions' in page.text
        assert '/live/activity' in page.text
        assert 'Checking execution state' in page.text
        assert "api('/system/state')" in page.text
        assert '/terminal/ticker' in page.text and '/terminal/market' in page.text
        assert 'devicePixelRatio' in page.text  # crisp canvas chart, not a stretched SVG
        assert 'this page cannot place orders' in page.text
        # Only GET requests, except device alert subscription under /push/ (never trading).
        import re
        assert page.text.count('method:') == 1 and "post('/push/" in page.text
        assert not re.search(r"post\('/(?!push/)", page.text)
        broker = client.get('/brokers/robinhood/status').json()
        assert broker['connected'] is False
        assert broker['execution_enabled'] is False


def test_ticker_uses_one_bounded_iex_snapshot_batch(monkeypatch):
    import app.main as main
    calls = []
    class Adapter:
        def _request(self, method, path, *, data_api, params):
            calls.append((method, path, data_api, params))
            if path == '/v1beta3/crypto/us/snapshots':
                return {'snapshots': {'BTC/USD': {
                    'latestQuote': {'t': '2026-09-22T20:00:00Z', 'bp': 100, 'ap': 101},
                    'latestTrade': {'t': '2026-09-22T20:00:00Z', 'p': 100.5},
                    'prevDailyBar': {'c': 100}}}}
            return {'SPY': {'latestQuote': {'t': '2026-09-22T20:00:00Z', 'bp': 10, 'ap': 10.02},
                            'latestTrade': {'t': '2026-09-22T20:00:00Z', 'p': 10},
                            'prevDailyBar': {'c': 9}}}
    monkeypatch.setattr(main.alpaca_connection, 'load_read_only_adapter', lambda *a, **k: (Adapter(), False))
    main._ticker_cache.update(expires_at=0, payload=None)
    result = terminal_ticker(db=object())
    assert len(calls) == 2
    assert calls[0][1] == '/v2/stocks/snapshots'
    assert calls[0][3]['feed'] == 'iex'
    assert result['source'] == 'Alpaca IEX + Crypto US'
    assert result['items'][0]['symbol'] == 'TQQQ'  # Stage Runner instrument first
    spy = next(x for x in result['items'] if x['symbol'] == 'SPY')
    assert spy['change_pct'] == 11.11
    assert result['items'][0]['price'] is None
    assert next(x for x in result['items'] if x['symbol'] == 'BTC/USD')['price'] == 100.5
    assert next(x for x in result['items'] if x['symbol'] == 'BTC/USD')['in_strategy_universe'] is False
    assert terminal_ticker(db=object()) is result
    assert len(calls) == 2
    main._ticker_cache.update(expires_at=0, payload=None)


def test_terminal_market_supports_intraday_candles(monkeypatch):
    import app.main as main
    calls = []
    class Adapter:
        def get_quotes(self, symbols):
            from types import SimpleNamespace
            return [SimpleNamespace(symbol='SPY', bid=100, ask=100.1, last=100.05,
                                    age_seconds=2, provider='alpaca')]
        def get_intraday_bars(self, symbol, start, end, *, timeframe):
            calls.append((symbol, timeframe, start, end))
            return [{'timestamp': '2026-09-22T19:00:00Z', 'open': 100,
                     'high': 101, 'low': 99, 'close': 100.5, 'volume': 1234}]
        def get_daily_bars(self, *args):
            raise AssertionError('daily bars should not be used for 5Min')
    monkeypatch.setattr(main.alpaca_connection, 'load_read_only_adapter', lambda *a, **k: (Adapter(), False))
    result = terminal_market(symbol='SPY', timeframe='5Min', db=object())
    assert result['timeframe'] == '5Min'
    assert result['source'] == 'Alpaca IEX'
    assert result['bars'][0]['close'] == 100.5
    assert calls[0][:2] == ('SPY', '5Min')


def test_terminal_market_crypto_is_read_only(monkeypatch):
    import app.main as main
    paths = []
    class Adapter:
        def _request(self, method, path, *, data_api, params):
            assert method == 'GET' and data_api is True
            paths.append(path)
            if path.endswith('/snapshots'):
                return {'snapshots': {'BTC/USD': {
                    'latestQuote': {'t': '2026-09-22T20:00:00Z', 'bp': 100, 'ap': 101},
                    'latestTrade': {'p': 100.5}}}}
            return {'bars': {'BTC/USD': [{'t': '2026-09-22T19:00:00Z', 'o': 99,
                                         'h': 101, 'l': 98, 'c': 100, 'v': 1234}]}}
    monkeypatch.setattr(main.alpaca_connection, 'load_read_only_adapter', lambda *a, **k: (Adapter(), False))
    result = terminal_market(symbol='BTC/USD', timeframe='5Min', db=object())
    assert result['source'] == 'Alpaca Crypto US'
    assert result['bars'][0]['close'] == 100
    assert paths == ['/v1beta3/crypto/us/snapshots', '/v1beta3/crypto/us/bars']


def test_activity_feed_is_bounded_and_read_only():
    with TestClient(app) as client:
        response = client.get('/paper/activity?limit=1')
        assert response.status_code == 200
        body = response.json()
        assert body['simulated'] is True
        assert len(body['events']) <= 1


def test_live_trade_feed_excludes_paper_executions():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            TradeDecisionRecord(symbol='ORCL', strategy='daily-trend-pullback-broad-equity-etf-v1',
                                direction='long', order_id='live-1', status='open', trade_id='live-trade'),
            AuditLogEntry(event_type='alpaca_live_worker_cycle_completed', payload={'trade_id': 'live-trade'}),
            TradeDecisionRecord(symbol='COP', strategy='daily-trend-pullback-expanded-equity-etf-v1',
                                direction='long', order_id='paper-1', status='open'),
            TradeDecisionRecord(symbol='AAPL', strategy='daily-trend-pullback-broad-equity-etf-v1',
                                direction='long', order_id='paper-broad-1', status='open'),
        ])
        db.commit()
        trades = live_trades(limit=20, db=db)['trades']
    assert [row['symbol'] for row in trades] == ['ORCL']


def test_decision_context_only_explains_audited_live_trade():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            TradeDecisionRecord(symbol='ORCL', strategy='daily-trend-pullback-broad-equity-etf-v1',
                                direction='long', order_id='live-1', trade_id='live-trade', status='open',
                                entry_thesis='daily trend pullback', stop_price=90, target_price=110,
                                risk_engine_result={'approved': True, 'reasons': []}),
            AuditLogEntry(event_type='alpaca_live_worker_cycle_completed', payload={'trade_id': 'live-trade'}),
            StrategyValidationRecord(strategy='daily-trend-pullback-broad-equity-etf-v1',
                                     methodology_version='test', trades=103, win_rate=.5,
                                     total_return=.136, max_drawdown=-.105, passed=True),
        ])
        db.commit()
        context = live_decision_context(db=db)
    assert context['latest_trade']['symbol'] == 'ORCL'
    assert context['latest_trade']['entry_thesis'] == 'daily trend pullback'
    assert context['live_validation']['trades'] == 103
    assert context['live_strategy']['maximum_open_positions_in_worker'] == 1


def test_dashboard_requires_password_when_configured(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "DASHBOARD_PASSWORD", "test-password")
    with TestClient(app) as client:
        assert client.get('/dashboard', follow_redirects=False).status_code == 303
        token = base64.b64encode(b"operator:test-password").decode()
        assert client.get('/dashboard', headers={"Authorization": f"Basic {token}"}).status_code == 200
        assert client.get('/brokers/robinhood/connect').status_code == 401

def test_dashboard_stage_cycle_and_unknown_balances_are_explicit():
    with TestClient(app) as client:
        page=client.get('/dashboard').text
        assert 'Milestone' in page and 'Allocator v1' in page
        assert 'annual target' not in page
        assert 'This does not mean the account is empty' in page
        assert '/live/milestones' in page and '/live/observer' in page
