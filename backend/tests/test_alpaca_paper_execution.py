from unittest.mock import MagicMock
from app.runtime.alpaca_paper_execution import execution_prerequisites

def test_external_paper_execution_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr('app.runtime.alpaca_paper_execution.load_read_only_adapter', lambda *_: (MagicMock(paper=True), True))
    cfg=MagicMock(ALPACA_PAPER_EXECUTION_ENABLED=False)
    assert execution_prerequisites(MagicMock(), cfg, 'AAPL')['reason'] == 'alpaca_paper_execution_gate_disabled'
