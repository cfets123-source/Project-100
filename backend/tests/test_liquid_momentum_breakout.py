from app.research.liquid_momentum_breakout import UNIVERSE, evaluate


def _bars(days=90):
    rows = []
    for day in range(days):
        price = 100.0 + day * 0.2
        rows.append({"timestamp": f"2023-01-{day + 1:03d}T00:00:00Z", "open": price,
                     "high": price + 1, "low": price - 1, "close": price,
                     "volume": 1_000_000})
    return rows


def test_breakout_portfolio_never_overlaps_positions():
    data = {symbol: _bars() for symbol in UNIVERSE}
    # Make one eligible close break through the prior range, then hit its stop.
    data["AAPL"][50].update(high=120, close=120, volume=2_000_000)
    data["AAPL"][51].update(low=100)
    trades = evaluate(data, split="2023-01-001T00:00:00Z")
    assert trades[0].symbol == "AAPL"
    assert trades[0].exit_reason == "stop"
    assert all(a.exit_timestamp <= b.entry_timestamp for a, b in zip(trades, trades[1:]))
