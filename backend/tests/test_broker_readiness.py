from app.services.broker_readiness import verify_read_only_connection


class ReadOnlyBroker:
    def __init__(self):
        self.trading_called = False

    def authenticate(self): return True
    def get_accounts(self): return [{"account_id": "agentic-100", "type": "agentic"}]
    def get_balances(self): return {"cash": 100.0, "equity": 100.0}
    def get_buying_power(self): return 100.0
    def get_positions(self): return []
    def get_orders(self): return []
    def preview_order(self, _): self.trading_called = True
    def place_order(self, _): self.trading_called = True
    def cancel_order(self, _): self.trading_called = True


def test_read_only_verification_never_invokes_trading_methods():
    broker = ReadOnlyBroker()
    result = verify_read_only_connection(broker, "agentic-100")
    assert result["connected"] is True
    assert result["read_only_ready"] is True
    assert result["execution_enabled"] is False
    assert broker.trading_called is False


def test_read_only_verification_rejects_wrong_account_or_invalid_cash():
    broker = ReadOnlyBroker()
    assert not verify_read_only_connection(broker, "wrong")["read_only_ready"]
    broker.get_balances = lambda: {"cash": float("nan"), "equity": 100.0}
    assert not verify_read_only_connection(broker, "agentic-100")["read_only_ready"]
