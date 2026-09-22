from datetime import datetime, timedelta, timezone

from app.research.intraday_trend_pullback import POSITION_ALLOCATION, ROUND_TRIP_COST, evaluate


def bars_for_day():
    start = datetime(2026, 9, 22, 13, 30, tzinfo=timezone.utc)
    rows = []
    for i in range(23):
        rows.append({"timestamp": (start + timedelta(minutes=i * 5)).isoformat(),
                     "open": 100, "high": 101, "low": 99.9, "close": 100, "volume": 1000})
    rows[20]["close"] = 100.6  # Above SMA but 0.4% below recent high.
    rows[21].update({"open": 100.7, "high": 101, "low": 100.5, "close": 101})
    rows[22].update({"open": 99, "high": 103, "low": 98, "close": 101})
    return rows


def test_next_bar_entry_gap_stop_first_and_account_sizing():
    rows = bars_for_day()
    trades = evaluate({"SPY": rows})
    assert trades[0].entry_timestamp == rows[21]["timestamp"]
    assert trades[0].exit_timestamp == rows[22]["timestamp"]
    assert trades[0].exit_reason == "stop"
    assert trades[0].applied_return == POSITION_ALLOCATION * (99 / 100.7 - 1 - ROUND_TRIP_COST)


def test_only_two_positions_can_be_open_at_once():
    rows = bars_for_day()
    rows[21].update({"open": 100.7, "high": 101, "low": 100.5, "close": 100.8})
    rows[22].update({"open": 100.8, "high": 101, "low": 100.5, "close": 100.8})
    trades = evaluate({symbol: rows for symbol in ("A", "B", "C")})
    assert len(trades) == 2
    assert {trade.symbol for trade in trades} == {"A", "B"}


def test_intraday_position_is_closed_at_last_observed_bar():
    rows = bars_for_day()
    rows[21].update({"open": 100.7, "high": 101, "low": 100.5, "close": 100.8})
    rows[22].update({"open": 100.8, "high": 101, "low": 100.5, "close": 100.8})
    trades = evaluate({"SPY": rows})
    assert trades[0].exit_reason == "last_bar_exit"
    assert trades[0].exit_timestamp == rows[22]["timestamp"]
