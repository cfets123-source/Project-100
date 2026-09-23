"""Frozen research-only end-of-day reversal candidate; no order path."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.research.intraday_trend_pullback import UNIVERSE

STRATEGY_VERSION = "intraday-end-of-day-reversal-portfolio-v1"
EASTERN = ZoneInfo("America/New_York")
SIGNAL_BAR = time(15, 20)
ENTRY_BAR = time(15, 30)
EXIT_BAR = time(15, 55)
OPEN_BAR = time(9, 30)
MIN_DROP = -.01
MIN_RELATIVE_RETURN = -.01
STOP_LOSS = .0075
TAKE_PROFIT = .015
POSITION_ALLOCATION = .40
MAX_POSITIONS = 2
ROUND_TRIP_COST = .001


@dataclass(frozen=True)
class Trade:
    day: str
    symbol: str
    relative_return: float
    entry_price: float
    exit_price: float
    exit_reason: str
    account_return: float


@dataclass(frozen=True)
class Result:
    trades: list[Trade]
    daily_returns: list[tuple[str, float]]
    missing_required_bars: int


def _session(timestamp: str) -> tuple[str, time]:
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("intraday bars require timezone-aware timestamps")
    local = instant.astimezone(EASTERN)
    return local.date().isoformat(), local.time()


def evaluate(data: dict[str, list[dict]], *, cost: float = ROUND_TRIP_COST) -> Result:
    if set(data) != set(UNIVERSE):
        raise ValueError("exact frozen 20-symbol universe required")
    if cost < 0:
        raise ValueError("cost cannot be negative")
    sessions: dict[str, dict[str, dict[time, dict]]] = {}
    for symbol, rows in data.items():
        by_day: dict[str, dict[time, dict]] = {}
        for row in rows:
            day, clock = _session(str(row["timestamp"]))
            if OPEN_BAR <= clock < time(16):
                by_day.setdefault(day, {})[clock] = row
        sessions[symbol] = by_day

    trades: list[Trade] = []
    daily_returns: list[tuple[str, float]] = []
    missing = 0
    for day in sorted(sessions["SPY"]):
        spy = sessions["SPY"][day]
        if OPEN_BAR not in spy or SIGNAL_BAR not in spy:
            missing += len(UNIVERSE) - 1
            continue
        spy_return = float(spy[SIGNAL_BAR]["close"]) / float(spy[OPEN_BAR]["open"]) - 1
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            if symbol == "SPY":
                continue
            bars = sessions[symbol].get(day, {})
            if not all(clock in bars for clock in (OPEN_BAR, SIGNAL_BAR, ENTRY_BAR, EXIT_BAR)):
                missing += 1
                continue
            opening = float(bars[OPEN_BAR]["open"])
            if opening <= 0:
                continue
            change = float(bars[SIGNAL_BAR]["close"]) / opening - 1
            relative = change - spy_return
            if change <= MIN_DROP and relative <= MIN_RELATIVE_RETURN:
                candidates.append((relative, symbol))
        account_return = 0.0
        for relative, symbol in sorted(candidates)[:MAX_POSITIONS]:
            bars = sessions[symbol][day]
            entry = float(bars[ENTRY_BAR]["open"])
            if entry <= 0:
                continue
            stop, target = entry * (1 - STOP_LOSS), entry * (1 + TAKE_PROFIT)
            exit_price, reason = float(bars[EXIT_BAR]["open"]), "session_close"
            for clock in sorted(t for t in bars if ENTRY_BAR <= t < EXIT_BAR):
                bar = bars[clock]
                if float(bar["low"]) <= stop:
                    exit_price, reason = min(float(bar["open"]), stop), "stop"
                    break
                if float(bar["high"]) >= target:
                    exit_price, reason = target, "target"
                    break
            applied = POSITION_ALLOCATION * (exit_price / entry - 1 - cost)
            trades.append(Trade(day, symbol, relative, entry, exit_price, reason, applied))
            account_return += applied
        daily_returns.append((day, account_return))
    return Result(trades, daily_returns, missing)
