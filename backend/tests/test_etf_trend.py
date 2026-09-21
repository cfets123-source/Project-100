from app.research.etf_trend import LOOKBACK_TREND, run


def _bar(value, *, low=None, high=None):
    return {"open": value, "high": high if high is not None else value * 1.01,
            "low": low if low is not None else value * .99, "close": value, "timestamp": "2020-01-01T00:00:00Z", "volume": 1}


def test_entry_is_next_open_and_stop_is_enforced():
    bars = [_bar(100) for _ in range(LOOKBACK_TREND)]
    bars += [_bar(102, high=103), _bar(104, low=95)]
    trades = run(bars, "SPY")
    assert len(trades) == 1
    assert trades[0].entry_index == LOOKBACK_TREND + 1
    assert trades[0].exit_reason == "protective_stop"
    assert trades[0].net_return < -.08


def test_open_trade_is_not_counted_as_result():
    bars = [_bar(100) for _ in range(LOOKBACK_TREND)] + [_bar(102, high=103), _bar(104)]
    assert run(bars, "SPY") == []
