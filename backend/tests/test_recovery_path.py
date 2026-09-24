import pytest

from app.research.recovery_path import assess_recovery_path


def test_loss_can_recover_and_then_reach_milestone():
    result = assess_recovery_path(
        [-.5, 1.0, 4.0], start_equity=100, target_equity=500,
        floor_equity=25,
    )
    assert result.target_day == 3
    assert result.end_equity == 500
    assert result.worst_drawdown == .5
    assert result.worst_drawdown_recovery_days == 1
    assert not result.floor_crossed


def test_unrecovered_loss_reports_remaining_hurdle():
    result = assess_recovery_path(
        [-.25, 0, .1], start_equity=100, target_equity=500,
    )
    assert result.target_day is None
    assert result.worst_drawdown_recovery_days is None
    assert result.longest_underwater_days == 3
    assert result.remaining_recovery_pct == pytest.approx(100 / 82.5 - 1)


def test_invalid_returns_fail_closed():
    with pytest.raises(ValueError):
        assess_recovery_path([-1.01], start_equity=100, target_equity=500)
