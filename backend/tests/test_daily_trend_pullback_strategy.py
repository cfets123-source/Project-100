import time

from app.strategies.daily_trend_pullback import (
    BroadDailyTrendPullback, BroadDailyTrendPullbackPortfolioV2, DailyTrendPullback,
)


class _Adapter:
    def get_daily_bars(self, symbol, start, end):
        rows = [{"close": 100.0, "high": 100.0, "timestamp": str(i)} for i in range(55)]
        rows[-1]["high"] = 105.0
        rows[-1]["close"] = 100.01
        return rows
    def get_quotes(self, symbols):
        class Quote:
            symbol = "SPY"
            last = 100.5
            bid = 100.4
            ask = 100.6
            timestamp = time.time()
            age_seconds = 0.0
        return [Quote()]


def test_daily_strategy_uses_current_quote_and_stable_daily_id():
    strategy = DailyTrendPullback()
    first = strategy.portfolio_signal(_Adapter(), ["SPY"])
    second = strategy.portfolio_signal(_Adapter(), ["SPY"])
    assert first["symbol"] == "SPY"
    assert first["entry_price"] == 100.5
    assert first["decision_id"] == second["decision_id"]
    assert first["technical_conditions"]["close"] == 100.01
    assert first["technical_conditions"]["five_day_high"] == 105.0
    assert first["technical_conditions"]["pullback_pct"] < -1.5


def test_broad_variant_has_an_independent_version_and_larger_universe():
    strategy = BroadDailyTrendPullback()
    assert strategy.name == "daily-trend-pullback-broad-equity-etf-v1"
    assert "AMD" in strategy.universe
    assert len(strategy.universe) > len(DailyTrendPullback().universe)


def test_portfolio_v2_returns_two_distinct_qualified_candidates():
    class PortfolioAdapter(_Adapter):
        def get_quotes(self, symbols):
            symbol = symbols[0]
            return [type("Quote", (), {"symbol": symbol, "last": 100.5, "bid": 100.4,
                                         "ask": 100.6, "timestamp": time.time(), "age_seconds": 0.0})()]

    signals = BroadDailyTrendPullbackPortfolioV2().portfolio_signals(
        PortfolioAdapter(), ["SPY", "QQQ"], limit=2,
    )
    assert {signal["symbol"] for signal in signals} == {"SPY", "QQQ"}
    assert len({signal["decision_id"] for signal in signals}) == 2
