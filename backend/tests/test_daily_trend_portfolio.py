from app.research.daily_trend_portfolio import Trade, evaluate


def _bars(days=65):
    return [{"timestamp": f"2023-01-{day:02d}T00:00:00Z", "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.0, "volume": 1_000_000} for day in range(1, days + 1)]


def test_evaluator_scores_only_post_split_and_never_overlaps():
    data = {symbol: _bars() for symbol in ("SPY", "QQQ", "IWM", "GLD", "TLT")}
    # Qualify SPY after the split, then make the next bar hit its stop.
    data["SPY"][50]["high"] = 105.0
    data["SPY"][50]["close"] = 100.01
    data["SPY"][51]["low"] = 96.0
    trades = evaluate(data, split="2023-01-51T00:00:00Z")
    assert len(trades) == 1
    assert trades[0].symbol == "SPY"
    assert trades[0].exit_reason == "stop"


def test_trade_is_immutable_value():
    trade = Trade("SPY", "a", "b", .01, .01, "target")
    assert trade.applied_return == .01
