from datetime import date, timedelta

import pytest

from app.research.daily_trend_portfolio_v2 import UNIVERSE, evaluate


def test_two_positions_share_cash_and_enter_after_signal_day():
    dates = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(56)]
    data = {symbol: [{"timestamp": day, "open": 100, "high": 100,
                      "low": 100, "close": 100, "volume": 1000} for day in dates]
            for symbol in UNIVERSE}
    for symbol in ("AAPL", "MSFT"):
        for bar in data[symbol][:50]:
            bar.update({"open": 99, "high": 99, "low": 99, "close": 99})
        data[symbol][50]["high"] = 110  # qualifying pullback on completed day 50
        data[symbol][51]["high"] = 100  # entry is next open, not signal-day high
        data[symbol][52]["high"] = 106  # both reach target after entry
    result = evaluate(data, split=dates[50], risk_per_trade=.02)
    assert result.max_concurrent_positions == 2
    assert len(result.trades) == 2
    assert all(trade.entry_timestamp == dates[51] for trade in result.trades)
    assert all(trade.exit_timestamp == dates[52] for trade in result.trades)
    final_equity = 1
    for value in result.daily_returns:
        final_equity *= 1 + value
    assert final_equity == pytest.approx(1.059)


def test_gap_below_stop_uses_open_not_optimistic_stop_fill():
    dates = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(55)]
    data = {symbol: [{"timestamp": day, "open": 100, "high": 100,
                      "low": 100, "close": 100, "volume": 1000} for day in dates]
            for symbol in UNIVERSE}
    data["AAPL"][50]["high"] = 110
    for bar in data["AAPL"][:50]:
        bar.update({"open": 99, "high": 99, "low": 99, "close": 99})
    data["AAPL"][51]["low"] = 100
    data["AAPL"][52].update({"open": 90, "high": 92, "low": 89, "close": 91})
    result = evaluate(data, split=dates[50])
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop"
    assert result.trades[0].raw_return == pytest.approx(-.101)
