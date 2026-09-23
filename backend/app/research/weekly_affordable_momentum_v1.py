"""Frozen whole-share weekly momentum research; never submits broker orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor

STRATEGY_VERSION = "weekly-affordable-momentum-whole-share-v1"
UNIVERSE = ("BAC", "CMCSA", "KO", "MDT", "NEE", "NKE", "PFE", "PYPL",
            "SBUX", "TLT", "UBER", "UPS", "USB")
STARTING_CASH = 100.0
MAX_EXPOSURE = .90
LOOKBACK = 63
TREND_DAYS = 100
STOP = .05
TARGET = .10
MAX_HOLD_DAYS = 10
ROUND_TRIP_COST = .001


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_day: str
    exit_day: str
    shares: int
    entry: float
    exit: float
    reason: str
    pnl: float


@dataclass(frozen=True)
class Result:
    trades: list[Trade]
    equity: list[tuple[str, float]]
    open_at_end: bool
    unavailable_entries: int


def evaluate(data: dict[str, list[dict]], *, adjustment: str,
             cost: float = ROUND_TRIP_COST) -> Result:
    if adjustment != "raw":
        raise ValueError("whole-share sizing requires raw historical prices")
    if set(data) != set(UNIVERSE):
        raise ValueError("exact fixed universe required")
    if cost < 0:
        raise ValueError("cost cannot be negative")
    rows = {symbol: {str(row["timestamp"])[:10]: row for row in data[symbol]}
            for symbol in UNIVERSE}
    dates = sorted(set.intersection(*(set(series) for series in rows.values())))
    cash = STARTING_CASH
    position: tuple[str, int, float, str, int] | None = None
    pending: list[str] = []
    trades: list[Trade] = []
    equity: list[tuple[str, float]] = []
    unavailable = 0
    for index in range(TREND_DAYS, len(dates)):
        day = dates[index]
        exited = False
        if position is None and pending:
            for symbol in pending:
                opening = float(rows[symbol][day]["open"])
                if opening <= 0:
                    continue
                shares = floor(min(cash / (1 + cost / 2),
                                   cash * MAX_EXPOSURE) / opening)
                if shares:
                    cash -= shares * opening * (1 + cost / 2)
                    position = (symbol, shares, opening, day, 0)
                    break
            if position is None:
                unavailable += 1
        pending = []
        if position is not None:
            symbol, shares, entry, entry_day, held = position
            bar = rows[symbol][day]
            opening, low, high, close = (float(bar[field]) for field in
                                         ("open", "low", "high", "close"))
            stop_price, target_price = entry * (1 - STOP), entry * (1 + TARGET)
            if low <= stop_price:
                exit_price, reason = min(opening, stop_price), "stop"
            elif high >= target_price:
                exit_price, reason = target_price, "target"
            elif held + 1 >= MAX_HOLD_DAYS:
                exit_price, reason = close, "time"
            else:
                exit_price = None
            if exit_price is not None:
                cash += shares * exit_price * (1 - cost / 2)
                trades.append(Trade(symbol, entry_day, day, shares, entry,
                                    exit_price, reason,
                                    shares * (exit_price * (1 - cost / 2)
                                              - entry * (1 + cost / 2))))
                position = None
                exited = True
            else:
                position = (symbol, shares, entry, entry_day, held + 1)
        mark = cash
        if position is not None:
            mark += position[1] * float(rows[position[0]][day]["close"])
        equity.append((day, mark))
        if position is not None or exited or index == len(dates) - 1:
            continue
        if date.fromisoformat(day).weekday() != 4:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            history = [rows[symbol][d] for d in dates[index - TREND_DAYS + 1:index + 1]]
            current = float(history[-1]["close"])
            average = sum(float(bar["close"]) for bar in history) / TREND_DAYS
            prior = float(rows[symbol][dates[index - LOOKBACK]]["close"])
            if prior > 0 and current > average and current / prior > 1:
                candidates.append((current / prior - 1, symbol))
        pending = [symbol for _, symbol in sorted(candidates, key=lambda item: (-item[0], item[1]))]
    return Result(trades, equity, position is not None, unavailable)
