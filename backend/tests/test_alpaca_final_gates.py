from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.runtime.alpaca_live_execution import load_finally_authorized_adapter
from app.runtime.alpaca_paper_lifecycle import run_once


def test_lifecycle_refuses_when_paper_execution_gate_is_off():
    assert run_once(MagicMock(), SimpleNamespace(ALPACA_PAPER_EXECUTION_ENABLED=False), 'AAPL')['reason'] == 'paper_execution_gate_disabled'


def test_live_adapter_refuses_before_final_live_gate(monkeypatch):
    state = MagicMock(); state.live_broker_mutation_allowed.return_value = (False, 'live_trading_hard_disabled_in_config')
    monkeypatch.setattr('app.runtime.alpaca_live_execution.StateManager', lambda *_: state)
    with pytest.raises(RuntimeError, match='hard_disabled'):
        load_finally_authorized_adapter(MagicMock(), SimpleNamespace(), "test-dip-buy-v0.1.0")
