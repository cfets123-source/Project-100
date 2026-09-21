from app.strategies.daily_trend_pullback import DailyTrendPullback


class _Adapter:
    def get_daily_bars(self, symbol, start, end):
        rows = [{"close": 100.0, "high": 100.0, "timestamp": str(i)} for i in range(55)]
        rows[-1]["high"] = 105.0
        rows[-1]["close"] = 100.01
        return rows
    def get_quotes(self, symbols):
        class Quote: symbol = "SPY"; last = 100.5
        return [Quote()]


def test_daily_strategy_uses_current_quote_and_stable_daily_id():
    strategy = DailyTrendPullback()
    first = strategy.portfolio_signal(_Adapter(), ["SPY"])
    second = strategy.portfolio_signal(_Adapter(), ["SPY"])
    assert first["symbol"] == "SPY"
    assert first["entry_price"] == 100.5
    assert first["decision_id"] == second["decision_id"]
