from unittest.mock import MagicMock
from app.runtime.alpaca_paper_execution_worker import run_cycle

def test_worker_never_loads_broker_when_paper_gate_is_off(monkeypatch):
    monkeypatch.setattr('app.runtime.alpaca_paper_execution_worker.run_reconciliation_cycle', lambda *_: {'market_open':True})
    loader=MagicMock(); monkeypatch.setattr('app.runtime.alpaca_paper_execution_worker.load_read_only_adapter', loader)
    cfg=MagicMock(ALPACA_PAPER_EXECUTION_ENABLED=False)
    result=run_cycle(MagicMock(), cfg, 'acct', ['AAPL'], {})
    assert result['entries']==[]
    loader.assert_not_called()
