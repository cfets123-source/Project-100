import pytest

from app.research.stage_distribution import assess_stage_distribution


def test_stage_test_uses_milestone_and_preserves_losing_streaks():
    history = [0.08] * 30 + [-0.08] * 30
    result = assess_stage_distribution(history, start_equity=100,
        target_equity=200, horizon_days=60, block_days=5, paths=1000, seed=7)
    assert result.observed_target_day == 10
    assert 0 < result.target_fraction < 1
    assert result.floor_fraction > 0
    assert result.ending_equity_p10 < result.ending_equity_p90


def test_stage_test_rejects_short_history_and_invalid_loss():
    with pytest.raises(ValueError, match="insufficient"):
        assess_stage_distribution([0.01] * 59, start_equity=100,
            target_equity=1000, horizon_days=60)
    with pytest.raises(ValueError, match="insufficient"):
        assess_stage_distribution([0.01] * 59 + [-1.0], start_equity=100,
            target_equity=1000, horizon_days=60)
