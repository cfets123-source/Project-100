import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers import alpaca_connection
from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import BrokerConnection


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


class StubAdapter:
    def __init__(self, *_args, **_kwargs): pass
    def authenticate(self): return True
    def get_accounts(self): return [{'account_id': 'paper-account'}]
    def get_balances(self): return {'equity': 100.0, 'cash': 100.0, 'buying_power': 100.0}
    def get_buying_power(self): return 100.0
    def get_positions(self): return []
    def get_orders(self): return []


def test_connect_encrypts_credential_and_readiness_never_enables_execution(db, monkeypatch):
    monkeypatch.setattr(alpaca_connection, 'AlpacaBrokerAdapter', StubAdapter)
    key = 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE='
    connected = alpaca_connection.connect(db, 'key', 'secret', key, paper=True)
    stored = db.get(BrokerConnection, 'alpaca_trading')
    assert connected['execution_enabled'] is False
    assert 'secret' not in stored.encrypted_refresh_token
    ready = alpaca_connection.verify_read_only(db, key)
    assert ready['read_only_ready'] is True
    assert ready['execution_enabled'] is False
    assert ready['paper'] is True
    assert ready['balances']['buying_power'] == 100.0
    assert ready['open_positions'] == 0 and ready['open_orders'] == 0


def test_live_read_only_credential_is_separate_from_paper(db, monkeypatch):
    monkeypatch.setattr(alpaca_connection, 'AlpacaBrokerAdapter', StubAdapter)
    key = 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE='
    alpaca_connection.connect(db, 'paper-key', 'paper-secret', key, paper=True)
    alpaca_connection.connect(db, 'live-key', 'live-secret', key, paper=False)

    paper_adapter, paper = alpaca_connection.load_read_only_adapter(db, key, paper=True)
    live_adapter, live = alpaca_connection.load_read_only_adapter(db, key, paper=False)

    assert paper is True and live is False
    assert db.get(BrokerConnection, alpaca_connection.PAPER_BROKER) is not None
    assert db.get(BrokerConnection, alpaca_connection.LIVE_BROKER) is not None
    assert paper_adapter is not live_adapter
