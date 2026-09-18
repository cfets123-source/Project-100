from app.brokers import alpaca_connection
from app.models.models import BrokerConnection


class StubAdapter:
    def __init__(self, *_args, **_kwargs): pass
    def authenticate(self): return True
    def get_accounts(self): return [{'account_id': 'paper-account'}]
    def get_balances(self): return {'buying_power': 100.0}


def test_connect_encrypts_credential_and_readiness_never_enables_execution(db, monkeypatch):
    monkeypatch.setattr(alpaca_connection, 'AlpacaBrokerAdapter', StubAdapter)
    key = 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE='
    connected = alpaca_connection.connect(db, 'key', 'secret', key, paper=True)
    stored = db.get(BrokerConnection, 'alpaca_trading')
    assert connected['execution_enabled'] is False
    assert 'secret' not in stored.encrypted_refresh_token
    ready = alpaca_connection.verify_read_only(db, key)
    assert ready == {'read_only_ready': True, 'paper': True, 'account_count': 1,
                     'buying_power': 100.0, 'execution_enabled': False}
