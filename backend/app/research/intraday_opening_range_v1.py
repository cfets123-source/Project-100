"""Frozen, research-only opening-range hypothesis for independent evaluation.

Signals use completed five-minute bars. Fills use the next bar open; exits
assume the worse stop when both stop and target are touched in one bar.
This module cannot submit broker orders or make a strategy live-eligible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from statistics import median
from zoneinfo import ZoneInfo

STRATEGY_VERSION = "intraday-opening-range-volume-v1"
UNIVERSE = ("SPY", "QQQ", "IWM", "XLK", "SMH", "XLF", "XLE", "GLD", "AAPL", "AMD",
            "AMZN", "AVGO", "GOOGL", "META", "MSFT", "NVDA", "ORCL", "PLTR", "TSLA", "V")
EASTERN = ZoneInfo("America/New_York")
STOP_LOSS = .03
TAKE_PROFIT = .045
ROUND_TRIP_COST = .001
POSITION_ALLOCATION = .50
MAX_POSITIONS = 2
MAX_ENTRIES_PER_DAY = 6
DAILY_LOSS_LIMIT = -.05
BREAKOUT_BUFFER = .001
VOLUME_MULTIPLIER = 1.2


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_timestamp: str
    exit_timestamp: str
    applied_return: float
    exit_reason: str


def _local(timestamp: str) -> datetime:
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("intraday bars require timezone-aware timestamps")
    return instant.astimezone(EASTERN)


def _candidate(symbol: str, rows: list[dict]) -> tuple[Trade, float] | None:
    rows = [row for row in sorted(rows, key=lambda item: item["timestamp"])
            if time(9, 30) <= _local(str(row["timestamp"])).time() < time(16)]
    if len(rows) < 10:
        return None
    opening = [row for row in rows if _local(str(row["timestamp"])).time() < time(10)]
    if len(opening) < 6:
        return None
    opening_high = max(float(row["high"]) for row in opening[:6])
    volume_sum = 0.0
    price_volume_sum = 0.0
    for i, row in enumerate(rows):
        volume = max(0.0, float(row.get("volume") or 0))
        typical = (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3
        volume_sum += volume
        price_volume_sum += typical * volume
        clock = _local(str(row["timestamp"])).time()
        if clock < time(10) or clock > time(14, 30) or i < 6 or i + 1 >= len(rows):
            continue
        if volume_sum <= 0:
            continue
        prior_volume = median(max(0.0, float(item.get("volume") or 0)) for item in rows[i - 6:i])
        if prior_volume <= 0:
            continue
        close = float(row["close"])
        volume_ratio = volume / prior_volume
        if (close <= opening_high * (1 + BREAKOUT_BUFFER)
                or close <= price_volume_sum / volume_sum
                or volume_ratio < VOLUME_MULTIPLIER):
            continue
        next_row = rows[i + 1]
        next_local = _local(str(next_row["timestamp"]))
        if next_local.date() != _local(str(row["timestamp"])).date():
            continue
        if (next_local - _local(str(row["timestamp"]))).total_seconds() != 300:
            continue
        entry = float(next_row["open"])
        if entry <= 0:
            continue
        stop, target = entry * (1 - STOP_LOSS), entry * (1 + TAKE_PROFIT)
        exit_row, exit_price, reason = next_row, float(next_row["close"]), "session_exit"
        for future in rows[i + 1:]:
            if _local(str(future["timestamp"])).date() != next_local.date():
                break
            exit_row = future
            if float(future["low"]) <= stop:
                exit_price, reason = min(float(future["open"]), stop), "stop"
                break
            if float(future["high"]) >= target:
                exit_price, reason = target, "target"
                break
            exit_price = float(future["close"])
            if _local(str(future["timestamp"])).time() >= time(15, 45):
                break
        applied = POSITION_ALLOCATION * (exit_price / entry - 1 - ROUND_TRIP_COST)
        return Trade(symbol, str(next_row["timestamp"]), str(exit_row["timestamp"]),
                     applied, reason), volume_ratio
    return None


def evaluate(bars_by_symbol: dict[str, list[dict]]) -> list[Trade]:
    """Select at most two overlapping positions from each day's first breakouts."""
    candidates: list[tuple[Trade, float]] = []
    for symbol, rows in bars_by_symbol.items():
        sessions: dict[str, list[dict]] = {}
        for row in rows:
            local = _local(str(row["timestamp"]))
            sessions.setdefault(local.date().isoformat(), []).append(row)
        for session_rows in sessions.values():
            result = _candidate(symbol, session_rows)
            if result is not None:
                candidates.append(result)
    accepted: list[Trade] = []
    open_trades: list[Trade] = []
    day, realized, entries = None, 0.0, 0
    for trade, volume_ratio in sorted(candidates, key=lambda item:
                                      (item[0].entry_timestamp, -item[1], item[0].symbol)):
        session = _local(trade.entry_timestamp).date()
        if session != day:
            day, realized, entries, open_trades = session, 0.0, 0, []
        finished = [item for item in open_trades
                    if item.exit_timestamp <= trade.entry_timestamp]
        realized += sum(item.applied_return for item in finished)
        open_trades = [item for item in open_trades if item not in finished]
        if (realized <= DAILY_LOSS_LIMIT or entries >= MAX_ENTRIES_PER_DAY
                or len(open_trades) >= MAX_POSITIONS):
            continue
        accepted.append(trade)
        open_trades.append(trade)
        entries += 1
    return sorted(accepted, key=lambda item: (item.exit_timestamp, item.symbol))
