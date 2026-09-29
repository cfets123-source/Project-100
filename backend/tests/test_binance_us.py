import hashlib
import hmac
import json
from urllib.parse import urlencode
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.brokers import binance_us as b
from app.brokers.robinhood_oauth import BrokerOAuthConfigurationError
from app.db.session import Base, get_db
from app.models.models import BrokerConnection
from app.main import app
from app.core.config import settings

ENC = 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE='
KEY, SECRET = 'K' * 64, 'S' * 64


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_signed_reads_and_allowlist(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={'serverTime': 1790000000000} if url.endswith('/time') else {'uid': 1234, 'balances': [], 'canTrade': True})
    monkeypatch.setattr(b.httpx, 'get', get)
    reader = b.BinanceUSReader(KEY, SECRET)
    assert reader.account()['uid'] == '1234'
    url, kwargs = calls[-1]
    params = kwargs['params'].copy()
    signature = params.pop('signature')
    assert signature == hmac.new(SECRET.encode(), urlencode(params).encode(), hashlib.sha256).hexdigest()
    assert kwargs['headers'] == {'X-MBX-APIKEY': KEY}
    assert kwargs['follow_redirects'] is False
    assert calls[0][1]['headers'] == {}
    with pytest.raises(b.BinanceError, match='Unsupported'):
        reader.get('/sapi/v1/capital/withdraw/apply')
    assert len(calls) == 2


def test_encryption_account_binding_and_failed_replacement(db, monkeypatch):
    uid = ['1234']
    monkeypatch.setattr(b.BinanceUSReader, 'account', lambda self: {'uid': uid[0]})
    assert b.connect(db, KEY, SECRET, ENC)['execution_enabled'] is False
    row = db.get(BrokerConnection, b.BROKER)
    original = row.encrypted_refresh_token
    assert SECRET not in original and KEY not in original
    assert b._decode(row, ENC)['api_secret'] == SECRET
    uid[0] = '5678'
    with pytest.raises(b.BinanceError, match='different account'):
        b.connect(db, KEY, SECRET, ENC)
    assert row.encrypted_refresh_token == original
    assert b.status(db)['credentials_saved']
    with pytest.raises(BrokerOAuthConfigurationError):
        b._decode(row, '')


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', None])
def test_invalid_balances_fail(value):
    with pytest.raises(b.BinanceError):
        b.amount(value)


def test_errors_do_not_disclose_credential_or_signature(monkeypatch):
    def fail(*a, **k):
        raise httpx.ConnectError('sensitive-url?signature='+SECRET)
    monkeypatch.setattr(b.httpx, 'get', fail)
    with pytest.raises(b.BinanceError) as error:
        b.BinanceUSReader(KEY, SECRET).account()
    assert SECRET not in str(error.value)


def test_readiness_reports_actual_fees_and_locked_balances(db, monkeypatch):
    def get(self, path, params=None):
        if path == '/api/v3/account':
            return {'uid': 1234, 'canTrade': False, 'balances': [{'asset':'USD','free':'90','locked':'10'}]}
        if path == '/api/v3/openOrders': return [{'symbol':'BTCUSD'}]
        return [{'symbol':s,'makerCommission':'0','takerCommission':'0.0002'} for s in b.SYMBOLS]
    monkeypatch.setattr(b.BinanceUSReader, 'get', get)
    b.connect(db, KEY, SECRET, ENC)
    report = b.readiness(db, ENC)
    assert report['balances'][0]['locked'] == '10'
    assert report['open_orders'] == 1
    assert report['read_only_ready'] and not report['broker_can_trade']
    assert not report['execution_enabled'] and report['fees'][0]['taker'] == '0.0002'
    assert KEY not in json.dumps(report) and 'uid' not in report


def test_routes_auth_csrf_and_no_secret_echo(monkeypatch):
    monkeypatch.setattr(settings, 'DASHBOARD_PASSWORD', 'protected')
    with TestClient(app) as client:
        for route in ('connect','status','readiness','markets'):
            assert client.get('/brokers/binance-us/'+route).status_code == 401
        assert client.post('/brokers/binance-us/connect', json={}).status_code == 401
        auth = (settings.DASHBOARD_USERNAME, 'protected')
        r = client.get('/brokers/binance-us/connect', auth=auth)
        assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
        assert 'frame-ancestors' in r.headers['content-security-policy']
        assert client.post('/brokers/binance-us/connect',auth=auth,json={}).status_code == 403
        r = client.post('/brokers/binance-us/connect',auth=auth,headers={'X-Veloikos-Setup':'binance-us','Origin':'https://evil.example'},json={})
        assert r.status_code == 403
        r = client.post('/brokers/binance-us/connect',auth=auth,headers={'X-Veloikos-Setup':'binance-us'},json={'api_key':KEY, 'api_secret':'bad secret'})
        assert r.status_code == 400 and KEY not in r.text and 'bad secret' not in r.text
