from app.research.intraday_morning_momentum_v1 import UNIVERSE, evaluate


def _bar(hour, minute, *, open_, low, close):
    return {"timestamp": f"2026-06-03T{hour:02d}:{minute:02d}:00-04:00",
            "open": open_, "high": max(open_, close), "low": low,
            "close": close, "volume": 100000}


def test_signal_uses_completed_morning_bar_and_enters_next_open():
    data = {symbol: [] for symbol in UNIVERSE}
    data["SPY"] = [
        _bar(9, 30, open_=100, low=99, close=100),
        _bar(11, 0, open_=100, low=99.9, close=101),
        _bar(11, 5, open_=102, low=101.5, close=102),
        _bar(15, 50, open_=104, low=80, close=80),
    ]

    result = evaluate(data)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == 102
    assert trade.exit_price == 104  # 15:50 open; its future low/close are unavailable
    assert trade.exit_reason == "session_exit"
    assert result.daily_returns[0][1] == trade.account_return


def test_stop_gap_uses_worse_open_and_stressed_cost_reduces_account_return():
    data = {symbol: [] for symbol in UNIVERSE}
    data["SPY"] = [
        _bar(9, 30, open_=100, low=99, close=100),
        _bar(11, 0, open_=100.2, low=100, close=101),
        _bar(11, 5, open_=102, low=101.5, close=102),
        _bar(11, 10, open_=100, low=99.5, close=100),
        _bar(15, 50, open_=104, low=103, close=104),
    ]

    base = evaluate(data).trades[0]
    stressed = evaluate(data, round_trip_cost=.002).trades[0]

    assert base.exit_reason == "stop"
    assert base.exit_price == 100  # worse than the 100.98 stop
    assert round(base.account_return - stressed.account_return, 8) == .0004
