from fastapi.testclient import TestClient
import base64
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import app, live_decision_context, live_trades
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
        assert "fetch('/system/state')" in page.text
        assert 'Connect Robinhood Agentic account' in page.text
        broker = client.get('/brokers/robinhood/status').json()
        assert broker['connected'] is False
        assert broker['execution_enabled'] is False


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
