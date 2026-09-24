"""Research-only monthly ETF rotation with fixed rules and no parameter search."""
from __future__ import annotations

STRATEGY_VERSION = "monthly-etf-rotation-v1"
UNIVERSE = ("SPY", "QQQ", "IWM")
MOMENTUM_DAYS = 126
TREND_DAYS = 200
ROUND_TRIP_COST = .001


def monthly_returns(by_symbol: dict[str, list[dict]], split: str) -> list[float]:
    """One-position monthly returns, entered/exited next-session open.

    At each month end, select the highest six-month return among ETFs above
    their 200-day mean. When none qualifies, hold cash.  Same-day ties follow
    the fixed UNIVERSE order. No data after the decision close is used.
    """
    reference = by_symbol[UNIVERSE[0]]
    dates = [row["timestamp"] for row in reference]
    index_by_date = {date: i for i, date in enumerate(dates)}
    month_ends = [i for i in range(1, len(dates) - 1) if dates[i][:7] != dates[i + 1][:7] and i >= TREND_DAYS]
    returns = []
    for current, nxt in zip(month_ends, month_ends[1:]):
        if dates[current] < split:
            continue
        candidates = []
        for symbol in UNIVERSE:
            bars = by_symbol[symbol]
            if current >= len(bars) or nxt + 1 >= len(bars):
                continue
            close = float(bars[current]["close"])
            trend = sum(float(x["close"]) for x in bars[current-TREND_DAYS+1:current+1]) / TREND_DAYS
            momentum = close / float(bars[current-MOMENTUM_DAYS]["close"]) - 1
            if close > trend:
                candidates.append((momentum, -UNIVERSE.index(symbol), symbol))
        if not candidates:
            continue
        symbol = max(candidates)[2]
        bars = by_symbol[symbol]
        entry, exit_ = float(bars[current + 1]["open"]), float(bars[nxt + 1]["open"])
        returns.append(exit_ / entry - 1 - ROUND_TRIP_COST)
    return returns
