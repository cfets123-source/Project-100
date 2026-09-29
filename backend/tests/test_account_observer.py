from unittest.mock import Mock
from app.core.config import Settings
from app.runtime import account_observer


def test_observer_forces_all_execution_flags_off(monkeypatch):
    seen=[]
    def supervise(db,cfg):
        seen.append(cfg)
        assert cfg.LIVE_TRADING_ENABLED is False
        assert cfg.LIVE_POSITION_MANAGEMENT_ENABLED is False
        assert cfg.AUTO_EXECUTION is False
        assert cfg.ALPACA_PAPER_EXECUTION_ENABLED is False
        assert cfg.ROBINHOOD_OPTIONS_EXECUTION_ENABLED is False
        return {'risk_ready':True,'positions':0,'milestone':{'phase':'accumulating','next_target':200}}
    monkeypatch.setattr(account_observer,'supervise_positions',supervise)
    monkeypatch.setattr(account_observer,'log_and_commit',lambda *a:None)
    cfg=Settings(LIVE_TRADING_ENABLED=True,LIVE_POSITION_MANAGEMENT_ENABLED=True,
                 ALPACA_PAPER_EXECUTION_ENABLED=True,ROBINHOOD_OPTIONS_EXECUTION_ENABLED=True)
    status=account_observer.observe_once(Mock(),cfg)
    assert status['read_only'] and not status['order_execution_enabled']
    assert cfg.LIVE_TRADING_ENABLED is True # did not mutate configuration shared by another process


def test_observer_reports_failure_instead_of_claiming_health(monkeypatch):
    def fail(*a): raise TimeoutError('sensitive broker response must not be printed')
    monkeypatch.setattr(account_observer,'supervise_positions',fail)
    monkeypatch.setattr(account_observer,'log_and_commit',lambda *a:None)
    status=account_observer.observe_once(Mock(),Settings())
    assert status['risk_ready'] is False and status['reason']=='TimeoutError'
