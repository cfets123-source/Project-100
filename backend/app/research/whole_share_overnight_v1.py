"""Cash and integer-share constrained overnight research; no broker orders."""
from __future__ import annotations

from dataclasses import dataclass
from math import floor

from app.research.daily_trend_portfolio import STOP_LOSS, TAKE_PROFIT, WARMUP_BARS
from app.research.run_expanded_daily_trend_validation import UNIVERSE

STRATEGY_VERSION = "daily-pullback-whole-share-overnight-v1"
STARTING_EQUITY = 100.0
MAX_EXPOSURE = .65
MAX_ACCOUNT_RISK = .02
ROUND_TRIP_COST = .001


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_day: str
    exit_day: str
    shares: int
    entry_price: float
    exit_price: float
    pnl: float
    reason: str


@dataclass(frozen=True)
class Result:
    trades: list[Trade]
    daily_equity: list[tuple[str, float]]
    unaffordable_signal_days: int
    open_position_at_end: bool


def evaluate(data: dict[str, list[dict]], *, cost: float = ROUND_TRIP_COST) -> Result:
    if set(data) != set(UNIVERSE):
        raise ValueError("exact expanded universe required")
    if cost < 0:
        raise ValueError("cost cannot be negative")
    indexed = {symbol: {str(row["timestamp"])[:10]: row for row in rows}
               for symbol, rows in data.items()}
    dates = sorted(set.intersection(*(set(rows) for rows in indexed.values())))
    cash = STARTING_EQUITY
    position: tuple[str, int, float, str] | None = None
    pending: list[str] = []
    trades: list[Trade] = []
    daily_equity: list[tuple[str, float]] = []
    unaffordable = 0
    for index in range(WARMUP_BARS - 1, len(dates)):
        day = dates[index]
        exited_today = False
        if position is None and pending:
            budget = min(cash / (1 + cost / 2),
                         daily_equity[-1][1] * MAX_EXPOSURE if daily_equity else cash * MAX_EXPOSURE,
                         (daily_equity[-1][1] if daily_equity else cash) * MAX_ACCOUNT_RISK / STOP_LOSS)
            for symbol in pending:
                entry = float(indexed[symbol][day]["open"])
                shares = floor(budget / entry) if entry > 0 else 0
                if shares >= 1:
                    cash -= shares * entry * (1 + cost / 2)
                    position = (symbol, shares, entry, day)
                    break
            if position is None:
                unaffordable += 1
        pending = []
        if position is not None:
            symbol, shares, entry, entry_day = position
            row = indexed[symbol][day]
            stop, target = entry * (1 - STOP_LOSS), entry * (1 + TAKE_PROFIT)
            if float(row["low"]) <= stop:
                exit_price, reason = min(float(row["open"]), stop), "stop"
            elif float(row["high"]) >= target:
                exit_price, reason = target, "target"
            else:
                exit_price = None
            if exit_price is not None:
                cash += shares * exit_price * (1 - cost / 2)
                pnl = shares * (exit_price - entry - cost * (entry + exit_price) / 2)
                trades.append(Trade(symbol, entry_day, day, shares, entry,
                                    exit_price, pnl, reason))
                position = None
                exited_today = True
        equity = cash
        if position is not None:
            symbol, shares, _, _ = position
            equity += shares * float(indexed[symbol][day]["close"])
        daily_equity.append((day, equity))
        if position is not None or exited_today or index == len(dates) - 1:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            rows = [indexed[symbol][date] for date in dates[index - 49:index + 1]]
            close = float(rows[-1]["close"])
            sma50 = sum(float(row["close"]) for row in rows) / 50
            high5 = max(float(row["high"]) for row in rows[-5:])
            pullback = close / high5 - 1
            if close > sma50 and pullback <= -.015:
                candidates.append((pullback, symbol))
        pending = [symbol for _, symbol in sorted(candidates)]
    return Result(trades, daily_equity, unaffordable, position is not None)
