from app.research.run_expanded_daily_trend_validation import STRATEGY_VERSION, UNIVERSE
from app.runtime.market_research_worker import EXPANDED_LIQUID_EQUITY_UNIVERSE


def test_expanded_validation_is_a_separate_bounded_research_universe():
    assert STRATEGY_VERSION == "daily-trend-pullback-expanded-equity-etf-v1"
    assert len(UNIVERSE) == len(set(UNIVERSE))
    assert set(EXPANDED_LIQUID_EQUITY_UNIVERSE).issubset(UNIVERSE)
    assert "ORCL" in UNIVERSE and "CRWD" in UNIVERSE
