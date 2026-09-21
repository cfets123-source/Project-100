"""Research-only liquid momentum-breakout portfolio.

This is deliberately a candidate, not a live strategy.  It uses liquid U.S.
equities and sector/index ETFs so the research can test a broader opportunity
set without relying on leverage or an illiquid micro-cap universe.
"""
from __future__ import annotations

from dataclasses import dataclass


STRATEGY_VERSION = "liquid-momentum-breakout-portfolio-v1"
UNIVERSE = (
    "AAPL", "AMD", "AMZN", "GOOGL", "META", "MSFT", "NFLX", "NVDA", "TSLA",
    "IWM", "QQQ", "SMH", "SPY", "XLE", "XLF", "XLK",
)
WARMUP_BARS = 50
BREAKOUT_DAYS = 20
MAX_HOLD_DAYS = 10
STOP_LOSS = 0.04
TAKE_PROFIT = 0.08
ROUND_TRIP_COST = 0.002


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_timestamp: str
    exit_timestamp: str
    raw_return: float
    applied_return: float
    exit_reason: str


def _aligned(data: dict[str, list[dict]]) -> tuple[list[str], dict[str, dict[str, dict]]]:
    indexed = {symbol: {str(row["timestamp"]): row for row in rows} for symbol, rows in data.items()}
    dates = sorted(set.intersection(*(set(rows) for rows in indexed.values())))
    return dates, indexed


def evaluate(data: dict[str, list[dict]], *, split: str) -> list[Trade]:
    """Evaluate chronological one-position breakout trades after ``split``.

    Signals use completed daily bars only.  A qualifying close must be above a
    50-day average, close through the previous 20-day high, and carry at least
    3% 20-day momentum.  Entry occurs at the *next* open; a stop, target, or
    ten-session time exit closes the one allowed position.
    """
    if set(data) != set(UNIVERSE):
        raise ValueError("data must contain exactly the liquid momentum universe")
    dates, indexed = _aligned(data)
    if len(dates) <= WARMUP_BARS + MAX_HOLD_DAYS + 1:
        return []

    trades: list[Trade] = []
    open_trade: tuple[str, float, float, float, int, str] | None = None
    for index in range(WARMUP_BARS, len(dates) - 1):
        date = dates[index]
        if open_trade is not None:
            symbol, entry, stop, target, entry_index, entry_timestamp = open_trade
            row = indexed[symbol][date]
            low, high, close = float(row["low"]), float(row["high"]), float(row["close"])
            # If both thresholds are crossed in a daily bar, take the adverse
            # stop result.  This avoids optimistic intraday ordering.
            if low <= stop:
                exit_price, reason = stop, "stop"
            elif high >= target:
                exit_price, reason = target, "target"
            elif index - entry_index >= MAX_HOLD_DAYS:
                exit_price, reason = close, "time_exit"
            else:
                continue
            raw = exit_price / entry - 1.0 - ROUND_TRIP_COST
            trades.append(Trade(symbol, entry_timestamp, date, raw, raw, reason))
            open_trade = None
            continue

        if date < split:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            rows = [indexed[symbol][item] for item in dates[index - WARMUP_BARS:index + 1]]
            close = float(rows[-1]["close"])
            sma50 = sum(float(row["close"]) for row in rows[-50:]) / 50
            prior_high = max(float(row["high"]) for row in rows[-BREAKOUT_DAYS - 1:-1])
            momentum = close / float(rows[-21]["close"]) - 1.0
            average_volume = sum(float(row["volume"]) for row in rows[-21:-1]) / 20
            volume_ratio = float(rows[-1]["volume"]) / average_volume if average_volume else 0.0
            if close > sma50 and close >= prior_high and momentum >= 0.03 and volume_ratio >= 1.0:
                candidates.append((momentum + 0.05 * (volume_ratio - 1.0), symbol))
        if candidates:
            _, symbol = max(candidates)
            entry_row = indexed[symbol][dates[index + 1]]
            entry = float(entry_row["open"])
            open_trade = (symbol, entry, entry * (1 - STOP_LOSS), entry * (1 + TAKE_PROFIT),
                          index + 1, dates[index + 1])
    return trades
