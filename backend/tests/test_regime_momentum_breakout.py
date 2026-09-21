from app.research.liquid_momentum_breakout import UNIVERSE
from app.research.regime_momentum_breakout import _exposure, evaluate


def _bars(days=230):
    return [{"timestamp": f"2023-01-{day + 1:03d}T00:00:00Z", "open": 100 + day * .2,
             "high": 101 + day * .2, "low": 99 + day * .2, "close": 100 + day * .2,
             "volume": 1_000_000} for day in range(days)]


def test_drawdown_pause_blocks_new_exposure():
    assert _exposure([], .89, 1.0) == 0.0


def test_regime_portfolio_has_one_position_at_a_time():
    data = {symbol: _bars() for symbol in UNIVERSE}
    data["AAPL"][200].update(high=150, close=150, volume=2_000_000)
    data["AAPL"][201].update(low=100)
    trades = evaluate(data, split="2023-01-001T00:00:00Z")
    assert trades[0].symbol == "AAPL"
    assert all(a.exit_timestamp <= b.entry_timestamp for a, b in zip(trades, trades[1:]))
