"""Research-only portfolio evaluator for a more frequent intraday hypothesis.

Completed five-minute bars produce signals; entries use the next bar open.
This module cannot place broker orders or authorize a strategy for live use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

STRATEGY_VERSION = "intraday-liquid-trend-pullback-portfolio-v3"
UNIVERSE = ("SPY", "QQQ", "IWM", "XLK", "SMH", "XLF", "XLE", "GLD", "AAPL", "AMD", "AMZN", "AVGO", "GOOGL", "META", "MSFT", "NVDA", "ORCL", "PLTR", "TSLA", "V")
WARMUP_BARS = 20
STOP_LOSS = .0075
TAKE_PROFIT = .015
ROUND_TRIP_COST = .001
MAX_POSITIONS = 2
POSITION_ALLOCATION = .40
DAILY_LOSS_LIMIT = -.015
MAX_ENTRIES_PER_DAY = 4
EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_timestamp: str
    exit_timestamp: str
    applied_return: float  # account return, after position allocation and costs
    exit_reason: str


def _session(timestamp: str) -> tuple[str, time]:
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("intraday bars require timezone-aware timestamps")
    local = instant.astimezone(EASTERN)
    return local.date().isoformat(), local.time()


def evaluate(bars_by_symbol: dict[str, list[dict]]) -> list[Trade]:
    """Two-slot, capital-limited simulation with no overnight positions."""
    indexed: dict[str, dict[str, tuple[int, dict]]] = {}
    regular: dict[str, list[dict]] = {}
    for symbol, rows in bars_by_symbol.items():
        session_rows = [row for row in sorted(rows, key=lambda item: item["timestamp"])
                        if time(9, 30) <= _session(str(row["timestamp"]))[1] < time(16)]
        regular[symbol] = session_rows
        indexed[symbol] = {str(row["timestamp"]): (i, row) for i, row in enumerate(session_rows)}
    stamps = sorted({stamp for rows in indexed.values() for stamp in rows})
    trades: list[Trade] = []
    positions: dict[str, tuple[float, str]] = {}
    day = None
    daily_pnl = 0.0
    entries_today = 0
    last_rows: dict[str, dict] = {}

    def close(symbol: str, stamp: str, price: float, reason: str) -> None:
        nonlocal daily_pnl
        entry, entered = positions.pop(symbol)
        account_return = POSITION_ALLOCATION * (price / entry - 1 - ROUND_TRIP_COST)
        trades.append(Trade(symbol, entered, stamp, account_return, reason))
        daily_pnl += account_return

    for stamp in stamps:
        session_day, clock = _session(stamp)
        if day != session_day:
            if positions:
                # Sparse data cannot silently carry a DAY-stop strategy overnight.
                for symbol in list(positions):
                    prior = last_rows[symbol]
                    close(symbol, str(prior["timestamp"]), float(prior["close"]), "last_bar_exit")
            day, daily_pnl, entries_today = session_day, 0.0, 0
        available = {symbol: index[stamp] for symbol, index in indexed.items() if stamp in index}
        for symbol in list(positions):
            if symbol not in available:
                continue
            _, row = available[symbol]
            entry, _ = positions[symbol]
            stop, target = entry * (1 - STOP_LOSS), entry * (1 + TAKE_PROFIT)
            # A gap through a stop fills at the worse opening price. When both
            # levels are touched within one bar, assume the stop fills first.
            if float(row["low"]) <= stop:
                close(symbol, stamp, min(float(row["open"]), stop), "stop")
            elif float(row["high"]) >= target:
                close(symbol, stamp, target, "target")
            elif clock >= time(15, 50):
                close(symbol, stamp, float(row["close"]), "session_exit")
        for symbol, (_, row) in available.items():
            last_rows[symbol] = row
        if clock >= time(15, 45) or daily_pnl <= DAILY_LOSS_LIMIT:
            continue
        if len(positions) >= MAX_POSITIONS or entries_today >= MAX_ENTRIES_PER_DAY:
            continue
        candidates = []
        for symbol, (i, row) in available.items():
            if symbol in positions or i < WARMUP_BARS or i + 1 >= len(regular[symbol]):
                continue
            next_row = regular[symbol][i + 1]
            next_day, next_clock = _session(str(next_row["timestamp"]))
            if next_day != session_day or next_clock > time(15, 45):
                continue
            closes = [float(item["close"]) for item in regular[symbol][i - 19:i + 1]]
            high = max(float(item["high"]) for item in regular[symbol][i - 4:i + 1])
            pullback = float(row["close"]) / high - 1
            if float(row["close"]) > sum(closes) / len(closes) and pullback <= -.003:
                candidates.append((pullback, symbol, next_row))
        for _, symbol, next_row in sorted(candidates):
            if len(positions) >= MAX_POSITIONS or entries_today >= MAX_ENTRIES_PER_DAY:
                break
            entry_stamp = str(next_row["timestamp"])
            positions[symbol] = (float(next_row["open"]), entry_stamp)
            entries_today += 1
    for symbol in list(positions):
        prior = last_rows[symbol]
        close(symbol, str(prior["timestamp"]), float(prior["close"]), "last_bar_exit")
    return sorted(trades, key=lambda trade: trade.exit_timestamp)
