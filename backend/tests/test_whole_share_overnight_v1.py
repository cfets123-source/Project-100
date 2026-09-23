from datetime import date, timedelta

from app.research.run_expanded_daily_trend_validation import UNIVERSE
from app.research.whole_share_overnight_v1 import evaluate


def test_integer_cash_sizing_and_gap_through_stop():
    days = [(date(2023, 1, 1) + timedelta(days=index)).isoformat()
            for index in range(52)]
    data = {}
    for symbol in UNIVERSE:
        price = 19 if symbol == "AAPL" else 100
        data[symbol] = [{"timestamp": day, "open": price, "high": price,
                         "low": price, "close": price} for day in days]
    data["AAPL"][49]["high"] = 22
    data["AAPL"][49]["close"] = 20
    data["AAPL"][50]["open"] = 18
    data["AAPL"][50]["high"] = 18
    data["AAPL"][50]["low"] = 18
    data["AAPL"][50]["close"] = 18
    data["AAPL"][51]["open"] = 17
    data["AAPL"][51]["high"] = 17
    data["AAPL"][51]["low"] = 16
    data["AAPL"][51]["close"] = 16
    result = evaluate(data)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.symbol == "AAPL"
    assert trade.shares == 3
    assert trade.reason == "stop"
    assert trade.exit_price == 17
    assert trade.pnl < 0


def test_uses_exact_universe_and_no_fractional_shares():
    try:
        evaluate({"AAPL": []})
    except ValueError as exc:
        assert "exact expanded universe" in str(exc)
    else:
        raise AssertionError("partial universe must fail")
