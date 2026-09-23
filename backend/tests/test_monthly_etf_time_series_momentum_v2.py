import pytest
from datetime import date, timedelta

from app.research.monthly_etf_time_series_momentum_v2 import UNIVERSE, evaluate


def test_v2_still_rejects_adjusted_prices_and_incomplete_universe():
    with pytest.raises(ValueError, match="raw prices"):
        evaluate({s: [] for s in UNIVERSE}, adjustment="all",
                 start="2022-01-01", end="2023-01-01")
    with pytest.raises(ValueError, match="exact ETF universe"):
        evaluate({"XLF": []}, adjustment="raw",
                 start="2022-01-01", end="2023-01-01")


def test_gap_through_stop_triggers_account_breaker():
    days = []
    current = date(2023, 1, 2)
    while len(days) < 460:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    data = {}
    for symbol in UNIVERSE:
        data[symbol] = []
        for index, day in enumerate(days):
            price = 20 + index * .03 if symbol == "XLF" else 20
            data[symbol].append({"timestamp": day, "open": price,
                                 "high": price, "low": price, "close": price})
    baseline = evaluate(data, adjustment="raw", start="2024-01-01", end="2025-01-01")
    assert baseline.trades
    first_entry = baseline.trades[0].entry_day
    next_index = days.index(first_entry) + 1
    gap = data["XLF"][next_index - 1]["close"] * .55
    data["XLF"][next_index].update(open=gap, high=gap, low=gap, close=gap)
    result = evaluate(data, adjustment="raw", start="2024-01-01", end="2025-01-01")
    assert result.breaker_events >= 1
    assert any(trade.reason == "stop" for trade in result.trades)
