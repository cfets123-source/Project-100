from unittest.mock import MagicMock
from app.runtime.alpaca_paper_reconciler import run_reconciliation_cycle

def test_reconciliation_cycle_refuses_live_credential(monkeypatch):
    monkeypatch.setattr('app.runtime.alpaca_paper_reconciler.load_read_only_adapter', lambda *_: (MagicMock(), False))
    try:
        run_reconciliation_cycle(MagicMock(), MagicMock(), ['AAPL'])
        assert False
    except RuntimeError as exc:
        assert 'refuses live' in str(exc)
