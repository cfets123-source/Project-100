"""Cash-constrained two-position evaluation of the broad daily selector.

Decisions use completed daily bars; entries occur at the next open. Each entry
can use at most half the portfolio, and overlapping positions share one cash
balance. This is research evidence, not a live strategy approval.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.research.daily_trend_portfolio import (ROUND_TRIP_COST, STOP_LOSS,
                                                 TAKE_PROFIT, WARMUP_BARS)
from app.strategies.daily_trend_pullback import BROAD_UNIVERSE, PORTFOLIO_BROAD_STRATEGY_VERSION

STRATEGY_VERSION = PORTFOLIO_BROAD_STRATEGY_VERSION
UNIVERSE = BROAD_UNIVERSE
MAX_POSITIONS = 2
MAX_POSITION_FRACTION = 0.5


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_timestamp: str
    exit_timestamp: str
    portfolio_pnl: float
    raw_return: float
    exit_reason: str


@dataclass(frozen=True)
class PortfolioResult:
    trades: list[Trade]
    daily_returns: list[float]
    max_concurrent_positions: int


def evaluate(data: dict[str, list[dict]], *, split: str,
             risk_per_trade: float = 0.01) -> PortfolioResult:
    if not 0 < risk_per_trade <= 0.03:
        raise ValueError("risk_per_trade must be between 0 and 3%")
    position_fraction = min(MAX_POSITION_FRACTION, risk_per_trade / STOP_LOSS)
    if not data or set(data) != set(UNIVERSE):
        raise ValueError("exact broad universe required")
    indexed = {symbol: {str(row["timestamp"]): row for row in bars}
               for symbol, bars in data.items()}
    dates = sorted(set.intersection(*(set(bars) for bars in indexed.values())))
    if len(dates) <= WARMUP_BARS + 2:
        return PortfolioResult([], [], 0)
    series = {symbol: [indexed[symbol][day] for day in dates] for symbol in UNIVERSE}
    cash = equity = 1.0
    # symbol -> entry, shares, principal, entry date
    positions: dict[str, tuple[float, float, float, str]] = {}
    pending: list[str] = []
    trades: list[Trade] = []
    daily_returns: list[float] = []
    max_concurrent = 0
    for index in range(WARMUP_BARS, len(dates)):
        day = dates[index]
        prior_equity = equity
        # Orders selected from the previous completed bar enter at this open.
        for symbol in pending:
            if symbol in positions or len(positions) >= MAX_POSITIONS:
                continue
            entry = float(series[symbol][index]["open"])
            if entry <= 0:
                continue
            mark_equity = cash + sum(
                shares * float(series[held][index - 1]["close"])
                for held, (_, shares, _, _) in positions.items())
            principal = min(cash, mark_equity * position_fraction)
            if principal <= 0:
                continue
            cash -= principal
            positions[symbol] = (entry, principal / entry, principal, day)
        pending = []
        max_concurrent = max(max_concurrent, len(positions))

        for symbol, (entry, shares, principal, entry_day) in list(positions.items()):
            bar = series[symbol][index]
            low, high = float(bar["low"]), float(bar["high"])
            if low <= entry * (1 - STOP_LOSS):
                exit_price, reason = min(float(bar["open"]), entry * (1 - STOP_LOSS)), "stop"
            elif high >= entry * (1 + TAKE_PROFIT):
                exit_price, reason = entry * (1 + TAKE_PROFIT), "target"
            else:
                continue
            raw = exit_price / entry - 1 - ROUND_TRIP_COST
            cash += principal * (1 + raw)
            trades.append(Trade(symbol, entry_day, day, principal * raw, raw, reason))
            del positions[symbol]

        equity = cash + sum(shares * float(series[symbol][index]["close"])
                            for symbol, (_, shares, _, _) in positions.items())
        if day >= split:
            daily_returns.append(equity / prior_equity - 1)
        if index >= len(dates) - 1 or day < split:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            if symbol in positions:
                continue
            rows = series[symbol]
            close = float(rows[index]["close"])
            sma50 = sum(float(item["close"]) for item in rows[index - 49:index + 1]) / 50
            high5 = max(float(item["high"]) for item in rows[index - 4:index + 1])
            pullback = close / high5 - 1
            if close > sma50 and pullback <= -0.015:
                candidates.append((pullback, symbol))
        pending = [symbol for _, symbol in sorted(candidates)[:MAX_POSITIONS - len(positions)]]
    return PortfolioResult(trades, daily_returns, max_concurrent)
