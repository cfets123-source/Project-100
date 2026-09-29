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


@pytest.mark.parametrize("strategy", [
    "daily-trend-pullback-portfolio-v1",
    "daily-trend-pullback-broad-equity-etf-v1",
    "daily-trend-pullback-expanded-equity-etf-v1",
    "daily-trend-pullback-broad-portfolio-v2",
])
def test_overnight_validation_cannot_authorize_fractional_day_stop_worker(monkeypatch, strategy):
    state = MagicMock()
    state.live_broker_mutation_allowed.return_value = (True, "allowed")
    monkeypatch.setattr("app.runtime.alpaca_live_execution.StateManager", lambda *_: state)
    validation = MagicMock(side_effect=RuntimeError("strategy_execution_contract_mismatch"))
    broker = MagicMock()
    monkeypatch.setattr("app.runtime.alpaca_live_execution.require_passing_validation", validation)
    monkeypatch.setattr("app.runtime.alpaca_live_execution.verify_read_only", broker)
    with pytest.raises(RuntimeError, match="strategy_execution_contract_mismatch"):
        load_finally_authorized_adapter(MagicMock(), SimpleNamespace(), strategy)
    validation.assert_called_once()
    broker.assert_not_called()
