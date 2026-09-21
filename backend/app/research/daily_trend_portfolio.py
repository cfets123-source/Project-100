"""Chronological, one-account evaluation for the daily trend-pullback idea.

This module is deliberately research-only.  It uses only a completed daily bar
to choose an entry at the *next* daily open; it never combines overlapping
single-symbol backtests into a fictitious portfolio result.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import stdev


STRATEGY_VERSION = "daily-trend-pullback-portfolio-v1"
UNIVERSE = ("SPY", "QQQ", "IWM", "GLD", "TLT")
WARMUP_BARS = 50
STOP_LOSS = 0.03
TAKE_PROFIT = 0.06
ROUND_TRIP_COST = 0.001  # conservative 10 bp entry + 10 bp exit estimate
TARGET_ANNUAL_VOL = 0.08
MAX_DRAWDOWN = 0.10


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_timestamp: str
    exit_timestamp: str
    raw_return: float
    applied_return: float
    exit_reason: str


def _index_by_timestamp(bars: list[dict]) -> dict[str, dict]:
    return {str(row["timestamp"]): row for row in bars}


def _exposure(closed_returns: list[float], equity: float, peak: float) -> float:
    """No-leverage volatility target with an irreversible 10% drawdown halt."""
    if equity < peak * (1 - MAX_DRAWDOWN):
        return 0.0
    trailing = closed_returns[-20:]
    if len(trailing) < 5:
        return 1.0
    realized_vol = stdev(trailing) * (252 ** 0.5)
    return min(1.0, TARGET_ANNUAL_VOL / realized_vol) if realized_vol else 1.0


def evaluate(data: dict[str, list[dict]], *, split: str) -> list[Trade]:
    """Return chronological trades opened on/after ``split``.

    Selection uses the largest pullback from a five-day high among symbols that
    remain above their 50-day moving average.  A position is entered next open,
    has a fixed 3% stop and 6% target, and is the only position held.
    """
    indexed = {symbol: _index_by_timestamp(rows) for symbol, rows in data.items()}
    dates = sorted(set.intersection(*(set(rows) for rows in indexed.values())))
    per_symbol = {symbol: [indexed[symbol][date] for date in dates] for symbol in indexed}
    trades: list[Trade] = []
    closed_returns: list[float] = []
    equity = peak = 1.0
    open_trade: tuple[str, float, float, float, str, float] | None = None

    for index in range(WARMUP_BARS, len(dates) - 1):
        date = dates[index]
        if open_trade is not None:
            symbol, entry, stop, target, entry_timestamp, exposure = open_trade
            row = per_symbol[symbol][index]
            # A bar that spans both thresholds receives the adverse stop fill.
            if float(row["low"]) <= stop:
                raw, reason = stop / entry - 1 - ROUND_TRIP_COST, "stop"
            elif float(row["high"]) >= target:
                raw, reason = target / entry - 1 - ROUND_TRIP_COST, "target"
            else:
                continue
            applied = raw * exposure
            trades.append(Trade(symbol, entry_timestamp, date, raw, applied, reason))
            closed_returns.append(applied)
            equity *= 1 + applied
            peak = max(peak, equity)
            open_trade = None
            continue

        if date < split or _exposure(closed_returns, equity, peak) == 0:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol, rows in per_symbol.items():
            close = float(rows[index]["close"])
            sma50 = sum(float(item["close"]) for item in rows[index - 49:index + 1]) / 50
            five_day_high = max(float(item["high"]) for item in rows[index - 4:index + 1])
            pullback = close / five_day_high - 1
            if close > sma50 and pullback <= -0.015:
                candidates.append((pullback, symbol))
        if candidates:
            _, symbol = min(candidates)  # deterministic: deepest qualifying pullback
            entry = float(per_symbol[symbol][index + 1]["open"])
            open_trade = (symbol, entry, entry * (1 - STOP_LOSS), entry * (1 + TAKE_PROFIT), dates[index + 1],
                          _exposure(closed_returns, equity, peak))
    return trades
