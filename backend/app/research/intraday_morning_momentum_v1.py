"""Frozen, research-only morning momentum portfolio evaluator.

All decisions use the completed 11:00 Eastern bar. Entries occur at the next
bar open; positions have no overnight carry. See the frozen research plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.research.intraday_trend_pullback import UNIVERSE

STRATEGY_VERSION = "intraday-morning-momentum-portfolio-v1"
EASTERN = ZoneInfo("America/New_York")
SIGNAL_TIME = time(11, 0)
ENTRY_TIME = time(11, 5)
EXIT_TIME = time(15, 50)
MIN_MORNING_RETURN = .006
MIN_PRICE = 5.0
STOP_LOSS = .01
POSITION_ALLOCATION = .40
MAX_POSITIONS = 2
ROUND_TRIP_COST = .001


@dataclass(frozen=True)
class Trade:
    symbol: str
    day: str
    morning_return: float
    entry_price: float
    exit_price: float
    exit_reason: str
    account_return: float


@dataclass(frozen=True)
class PortfolioResult:
    trades: list[Trade]
    daily_returns: list[tuple[str, float]]
    missing_required_bars: int


def _session(timestamp: str) -> tuple[str, time]:
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("bars must have timezone-aware timestamps")
    local = instant.astimezone(EASTERN)
    return local.date().isoformat(), local.time()


def evaluate(data: dict[str, list[dict]], *, round_trip_cost: float = ROUND_TRIP_COST) -> PortfolioResult:
    if set(data) != set(UNIVERSE):
        raise ValueError("exact frozen 20-symbol universe required")
    if round_trip_cost < 0:
        raise ValueError("cost cannot be negative")
    sessions: dict[str, dict[str, dict[time, dict]]] = {}
    for symbol, rows in data.items():
        by_day: dict[str, dict[time, dict]] = {}
        for row in rows:
            day, clock = _session(str(row["timestamp"]))
            if time(9, 30) <= clock < time(16):
                by_day.setdefault(day, {})[clock] = row
        sessions[symbol] = by_day

    trades: list[Trade] = []
    daily_returns: list[tuple[str, float]] = []
    missing = 0
    for day in sorted({day for by_day in sessions.values() for day in by_day}):
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            bars = sessions[symbol].get(day, {})
            required = (time(9, 30), SIGNAL_TIME, ENTRY_TIME, EXIT_TIME)
            if not all(clock in bars for clock in required):
                missing += 1
                continue
            morning_open = float(bars[time(9, 30)]["open"])
            signal_close = float(bars[SIGNAL_TIME]["close"])
            if morning_open < MIN_PRICE or signal_close < MIN_PRICE:
                continue
            morning_return = signal_close / morning_open - 1
            if morning_return >= MIN_MORNING_RETURN:
                candidates.append((morning_return, symbol))

        account_return = 0.0
        for morning_return, symbol in sorted(candidates, key=lambda item: (-item[0], item[1]))[:MAX_POSITIONS]:
            bars = sessions[symbol][day]
            entry = float(bars[ENTRY_TIME]["open"])
            if entry <= 0:
                continue
            stop = entry * (1 - STOP_LOSS)
            exit_price = float(bars[EXIT_TIME]["open"])
            reason = "session_exit"
            for clock in sorted(t for t in bars if ENTRY_TIME <= t < EXIT_TIME):
                bar = bars[clock]
                if float(bar["low"]) <= stop:
                    exit_price = min(float(bar["open"]), stop)
                    reason = "stop"
                    break
            applied = POSITION_ALLOCATION * (exit_price / entry - 1 - round_trip_cost)
            trades.append(Trade(symbol, day, morning_return, entry, exit_price, reason, applied))
            account_return += applied
        daily_returns.append((day, account_return))
    return PortfolioResult(trades, daily_returns, missing)
