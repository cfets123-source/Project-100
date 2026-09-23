from app.research.session_matched_daily import Signal, evaluate_session


def _bar(clock, high, low, open_=100):
    return {"timestamp": f"2026-06-01T{clock}:00Z", "open": open_,
            "high": high, "low": low, "close": open_}


def test_stop_wins_ambiguous_bar_and_session_exit_is_required():
    signal = Signal("2026-05-29", "2026-06-01", "SPY", -.02)
    rows = [_bar("13:30", 100, 100), _bar("14:00", 107, 96),
            _bar("19:15", 101, 101)]
    trade = evaluate_session(signal, rows)
    assert trade is not None
    assert trade.exit_reason == "stop"
    assert trade.exit_price == 97
    assert trade.account_return < 0
    assert evaluate_session(signal, rows[:-1]) is None


def test_session_exit_uses_first_price_at_close_window():
    signal = Signal("2026-05-29", "2026-06-01", "SPY", -.02)
    rows = [_bar("13:30", 101, 99), _bar("19:15", 102, 101, open_=101)]
    trade = evaluate_session(signal, rows)
    assert trade is not None
    assert trade.exit_reason == "session_close"
    assert trade.exit_price == 101
