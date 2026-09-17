import pytest
from pydantic import ValidationError
from app.core.config import Settings, TradingMode, AutonomyLevel


def test_default_settings_are_safe_and_valid():
    s = Settings()
    assert s.TRADING_MODE == TradingMode.PAPER
    assert s.AUTONOMY_LEVEL == AutonomyLevel.LEVEL_0_RESEARCH_ONLY
    assert s.AUTO_EXECUTION is False


def test_rejects_paper_mode_with_live_autonomy_level():
    with pytest.raises(ValidationError):
        Settings(TRADING_MODE=TradingMode.PAPER, AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS)


def test_rejects_live_mode_with_insufficient_autonomy_level():
    with pytest.raises(ValidationError):
        Settings(TRADING_MODE=TradingMode.LIVE, AUTONOMY_LEVEL=AutonomyLevel.LEVEL_1_CANDIDATES_ONLY)


def test_rejects_auto_execution_at_approval_required_level():
    with pytest.raises(ValidationError):
        Settings(TRADING_MODE=TradingMode.LIVE, AUTONOMY_LEVEL=AutonomyLevel.LEVEL_3_LIVE_NEEDS_APPROVAL,
                 AUTO_EXECUTION=True)


def test_allows_valid_live_autonomous_combination():
    s = Settings(TRADING_MODE=TradingMode.LIVE, AUTONOMY_LEVEL=AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS,
                  AUTO_EXECUTION=True)
    assert s.TRADING_MODE == TradingMode.LIVE


def test_allows_live_level_3_without_auto_execution():
    """LEVEL_3 = generates live orders requiring human approval; AUTO_EXECUTION
    must be False so nothing auto-submits."""
    s = Settings(TRADING_MODE=TradingMode.LIVE, AUTONOMY_LEVEL=AutonomyLevel.LEVEL_3_LIVE_NEEDS_APPROVAL,
                  AUTO_EXECUTION=False)
    assert s.AUTO_EXECUTION is False
