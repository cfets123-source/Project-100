from app.research.run_expanded_daily_trend_validation import STRATEGY_VERSION as VALIDATED_VERSION
from app.strategies.daily_trend_pullback import ExpandedDailyTrendPullback


def test_expanded_paper_worker_strategy_exactly_matches_validated_version():
    strategy = ExpandedDailyTrendPullback()
    assert strategy.name == VALIDATED_VERSION
    assert len(strategy.universe) == len(set(strategy.universe))
    assert "ORCL" in strategy.universe and "CRWD" in strategy.universe
