from app.research.end_of_day_reversal_v1 import evaluate
from app.research.intraday_trend_pullback import UNIVERSE


def _bar(clock, open_, high, low, close):
    return {"timestamp": f"2026-06-01T{clock}:00Z", "open": open_,
            "high": high, "low": low, "close": close}


def test_completed_signal_selects_relative_loser_and_stop_wins():
    baseline = [_bar("13:30", 100, 100, 100, 100),
                _bar("19:20", 100, 100, 100, 100),
                _bar("19:30", 100, 100, 100, 100),
                _bar("19:55", 100, 100, 100, 100)]
    data = {symbol: baseline for symbol in UNIVERSE}
    data["AAPL"] = [_bar("13:30", 100, 100, 100, 100),
                    _bar("19:20", 98, 98, 98, 98),
                    _bar("19:30", 98, 100, 96, 98),
                    _bar("19:55", 98, 98, 98, 98)]
    result = evaluate(data)
    assert len(result.trades) == 1
    assert result.trades[0].symbol == "AAPL"
    assert result.trades[0].exit_reason == "stop"
    assert result.trades[0].exit_price == 98 * (1 - .0075)
    assert result.trades[0].account_return < 0


def test_missing_exit_bar_excludes_candidate_instead_of_inventing_fill():
    baseline = [_bar("13:30", 100, 100, 100, 100),
                _bar("19:20", 100, 100, 100, 100),
                _bar("19:30", 100, 100, 100, 100),
                _bar("19:55", 100, 100, 100, 100)]
    data = {symbol: baseline for symbol in UNIVERSE}
    data["AAPL"] = [_bar("13:30", 100, 100, 100, 100),
                    _bar("19:20", 98, 98, 98, 98),
                    _bar("19:30", 98, 98, 98, 98)]
    result = evaluate(data)
    assert not result.trades
    assert result.missing_required_bars == 1
