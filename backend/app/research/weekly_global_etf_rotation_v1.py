"""Research-only weekly ETF rotation with raw-price whole-share sizing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor

STRATEGY_VERSION = "weekly-global-sector-etf-rotation-whole-share-v1"
UNIVERSE = ("XLF", "XLE", "XLP", "XLU", "XLRE", "XBI", "KRE", "HYG",
            "TLT", "FXI", "EWU", "EEM", "EWJ", "VWO")
LOOKBACK = 63
TREND_DAYS = 100
MAX_EXPOSURE = .90
STOP = .05
TARGET = .10
MAX_HOLD_DAYS = 10


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_day: str
    exit_day: str
    shares: int
    entry: float
    exit: float
    reason: str


@dataclass(frozen=True)
class Result:
    trades: list[Trade]
    equity: list[tuple[str, float]]
    unavailable_entries: int
    open_at_end: bool


def evaluate(data: dict[str, list[dict]], *, adjustment: str,
             start: str = "2022-01-01", end: str = "2026-09-23",
             cost: float = .001) -> Result:
    if adjustment != "raw" or set(data) != set(UNIVERSE):
        raise ValueError("exact ETF universe and raw prices required")
    if start >= end or cost < 0:
        raise ValueError("invalid range or cost")
    rows = {s: {str(r["timestamp"])[:10]: r for r in data[s]} for s in UNIVERSE}
    dates = sorted(set.intersection(*(set(series) for series in rows.values())))
    cash = 100.0
    position: tuple[str, int, float, str, int] | None = None
    pending: list[str] = []
    trades: list[Trade] = []
    equity: list[tuple[str, float]] = []
    unavailable = 0
    for index in range(TREND_DAYS, len(dates)):
        day = dates[index]
        if day >= end:
            break
        if day < start:
            continue
        exited = False
        if position is None and pending:
            for symbol in pending:
                opening = float(rows[symbol][day]["open"])
                shares = floor(min(cash * MAX_EXPOSURE, cash / (1 + cost / 2)) / opening) if opening > 0 else 0
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
            opening, low, high, close = (float(bar[k]) for k in ("open", "low", "high", "close"))
            if low <= entry * (1 - STOP):
                exit_price, reason = min(opening, entry * (1 - STOP)), "stop"
            elif high >= entry * (1 + TARGET):
                exit_price, reason = entry * (1 + TARGET), "target"
            elif held + 1 >= MAX_HOLD_DAYS:
                exit_price, reason = close, "time"
            else:
                exit_price = None
            if exit_price is not None:
                cash += shares * exit_price * (1 - cost / 2)
                trades.append(Trade(symbol, entry_day, day, shares, entry,
                                    exit_price, reason))
                position = None
                exited = True
            else:
                position = (symbol, shares, entry, entry_day, held + 1)
        marked = cash
        if position is not None:
            marked += position[1] * float(rows[position[0]][day]["close"])
        equity.append((day, marked))
        if position is not None or exited or date.fromisoformat(day).weekday() != 4:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            close = float(rows[symbol][day]["close"])
            average = sum(float(rows[symbol][d]["close"])
                          for d in dates[index - TREND_DAYS + 1:index + 1]) / TREND_DAYS
            prior = float(rows[symbol][dates[index - LOOKBACK]]["close"])
            if prior > 0 and close > average and close > prior:
                candidates.append((close / prior - 1, symbol))
        pending = [symbol for _, symbol in sorted(candidates, key=lambda x: (-x[0], x[1]))]
    return Result(trades, equity, unavailable, position is not None)
