"""Diagnostic for daily signals with the live fractional DAY-stop horizon.

This does not promote a strategy: historical IEX bars approximate fills and
the exact next-session broker quote, spread, and stop cancellation are unknown.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.research.daily_trend_portfolio import STOP_LOSS, TAKE_PROFIT, WARMUP_BARS
from app.research.run_expanded_daily_trend_validation import UNIVERSE

EASTERN = ZoneInfo("America/New_York")
ENTRY_BAR = time(9, 30)
SESSION_EXIT_BAR = time(15, 15)
POSITION_FRACTION = 1 / 3  # 1% account risk / 3% stop, capped below 50%
ROUND_TRIP_COST = .001


@dataclass(frozen=True)
class Signal:
    decision_day: str
    entry_day: str
    symbol: str
    pullback: float


@dataclass(frozen=True)
class Trade:
    signal: Signal
    entry_price: float
    exit_price: float
    exit_reason: str
    account_return: float


def select_signals(data: dict[str, list[dict]], *, start: str) -> list[Signal]:
    """Choose the deepest qualifying completed daily pullback across all 79."""
    if set(data) != set(UNIVERSE):
        raise ValueError("exact expanded universe required")
    indexed = {symbol: {str(row["timestamp"])[:10]: row for row in rows}
               for symbol, rows in data.items()}
    dates = sorted(set.intersection(*(set(rows) for rows in indexed.values())))
    signals: list[Signal] = []
    for index in range(WARMUP_BARS - 1, len(dates) - 1):
        day, entry_day = dates[index], dates[index + 1]
        if entry_day < start:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            rows = [indexed[symbol][date] for date in dates[index - 49:index + 1]]
            close = float(rows[-1]["close"])
            sma50 = sum(float(row["close"]) for row in rows) / 50
            high5 = max(float(row["high"]) for row in rows[-5:])
            if close > sma50 and close / high5 - 1 <= -.015:
                candidates.append((close / high5 - 1, symbol))
        if candidates:
            pullback, symbol = min(candidates)
            signals.append(Signal(day, entry_day, symbol, pullback))
    return signals


def evaluate_session(signal: Signal, rows: list[dict], *,
                     cost: float = ROUND_TRIP_COST) -> Trade | None:
    """Enter 9:30, stop/target on five-minute lows/highs, exit by 15:15.

    Missing entry or session-exit bars make that session unevaluable. A bar
    touching both stop and target takes the adverse stop. Gaps can worsen it.
    """
    if cost < 0:
        raise ValueError("cost cannot be negative")
    bars: dict[time, dict] = {}
    for row in rows:
        instant = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
        local = instant.astimezone(EASTERN)
        if local.date().isoformat() == signal.entry_day:
            bars[local.time()] = row
    if ENTRY_BAR not in bars or SESSION_EXIT_BAR not in bars:
        return None
    entry = float(bars[ENTRY_BAR]["open"])
    if entry <= 0:
        return None
    stop, target = entry * (1 - STOP_LOSS), entry * (1 + TAKE_PROFIT)
    exit_price = float(bars[SESSION_EXIT_BAR]["open"])
    reason = "session_close"
    for clock in sorted(t for t in bars if ENTRY_BAR <= t < SESSION_EXIT_BAR):
        bar = bars[clock]
        if float(bar["low"]) <= stop:
            exit_price, reason = min(float(bar["open"]), stop), "stop"
            break
        if float(bar["high"]) >= target:
            exit_price, reason = target, "target"
            break
    return Trade(signal, entry, exit_price, reason,
                 POSITION_FRACTION * (exit_price / entry - 1 - cost))
