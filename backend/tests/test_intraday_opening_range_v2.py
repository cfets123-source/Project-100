from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.research.intraday_opening_range_v2 import evaluate


def _bars(symbol, *, both_exits=False):
    start = datetime(2025, 1, 6, 9, 30, tzinfo=ZoneInfo("America/New_York"))
    rows = []
    for i in range(12):
        t = start + timedelta(minutes=5 * i)
        price = 100 if i < 6 else 101
        rows.append({"timestamp": t.isoformat(), "open": price, "high": price + .1,
                     "low": price - .1, "close": price, "volume": 100})
    rows[6].update(open=101, high=101.2, low=100.8, close=101.1, volume=180)
    if both_exits:
        rows[7].update(open=101, high=107, low=96, close=105)
    return rows


def test_next_bar_entry_and_stop_first_when_both_exits_touch():
    trades = evaluate({"AAPL": _bars("AAPL", both_exits=True)})
    assert len(trades) == 1
    assert trades[0].entry_timestamp.endswith("10:05:00-05:00")
    assert trades[0].exit_reason == "stop"
    assert trades[0].applied_return < 0


def test_portfolio_limits_overlapping_breakouts_to_two_slots():
    trades = evaluate({symbol: _bars(symbol) for symbol in ("AAPL", "AMD", "MSFT")})
    assert len(trades) == 2
