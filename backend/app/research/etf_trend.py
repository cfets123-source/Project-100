"""Fixed-specification, research-only ETF trend candidate.

This module is intentionally a backtest, not an execution strategy. It uses
only information available at each close and enters at the following open.
Parameters are fixed in source before an evaluation is run.
"""
from __future__ import annotations

from dataclasses import dataclass


STRATEGY_VERSION = "etf-trend-breakout-v1"
UNIVERSE = ("SPY", "QQQ", "IWM")
LOOKBACK_TREND = 200
LOOKBACK_BREAKOUT = 55
EXIT_LOOKBACK = 20
STOP_PCT = 0.08
ROUND_TRIP_COST = 0.001  # 10 bps for spread/slippage; deliberately conservative for liquid ETFs


@dataclass(frozen=True)
class CompletedTrade:
    symbol: str
    entry_index: int
    exit_index: int
    entry_timestamp: str
    exit_timestamp: str
    gross_return: float
    net_return: float
    exit_reason: str


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def run(bars: list[dict], symbol: str) -> list[CompletedTrade]:
    """Backtest the fixed rule without same-bar fill assumptions.

    Signal: close above 200-day average and a 55-day prior high. Entry is the
    next session open. Exit uses an 8% intraday stop or next-open exit after a
    close below the prior 20-day low. Open trades are excluded from results.
    """
    if len(bars) < LOOKBACK_TREND + 2:
        return []
    completed: list[CompletedTrade] = []
    position: dict | None = None
    pending_entry = False
    pending_exit = False
    for index, bar in enumerate(bars):
        if pending_entry:
            entry = float(bar["open"])
            position = {"entry": entry, "stop": entry * (1 - STOP_PCT), "entry_index": index}
            pending_entry = False
        elif pending_exit and position:
            gross = float(bar["open"]) / position["entry"] - 1
            completed.append(CompletedTrade(symbol, position["entry_index"], index,
                                            bars[position["entry_index"]]["timestamp"], bar["timestamp"], gross,
                                            gross - ROUND_TRIP_COST, "trend_exit"))
            position, pending_exit = None, False

        if position:
            if float(bar["low"]) <= position["stop"]:
                gross = position["stop"] / position["entry"] - 1
                completed.append(CompletedTrade(symbol, position["entry_index"], index,
                                                bars[position["entry_index"]]["timestamp"], bar["timestamp"], gross,
                                                gross - ROUND_TRIP_COST, "protective_stop"))
                position = None
            elif index >= EXIT_LOOKBACK:
                prior_lows = [float(row["low"]) for row in bars[index - EXIT_LOOKBACK:index]]
                if float(bar["close"]) < min(prior_lows):
                    pending_exit = True
            continue

        if index < LOOKBACK_TREND:
            continue
        prior = bars[:index]
        trend = _mean([float(row["close"]) for row in prior[-LOOKBACK_TREND:]])
        breakout = max(float(row["high"]) for row in prior[-LOOKBACK_BREAKOUT:])
        if float(bar["close"]) > trend and float(bar["close"]) > breakout:
            pending_entry = True
    return completed


def non_overlapping_portfolio_returns(trades: list[CompletedTrade]) -> list[float]:
    """One-account result series: fixed timestamp/symbol ordering, no overlap.

    The account cannot hold simultaneous positions under this research protocol.
    Sorting by symbol is only a deterministic tie-breaker for same-day signals;
    it is fixed here before any pass/fail decision.
    """
    returns: list[float] = []
    next_entry_allowed = ""
    for trade in sorted(trades, key=lambda item: (item.entry_timestamp, item.symbol)):
        if trade.entry_timestamp < next_entry_allowed:
            continue
        returns.append(trade.net_return)
        next_entry_allowed = trade.exit_timestamp
    return returns
