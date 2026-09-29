"""Settlement-corrected monthly ETF momentum research; no order path."""
from __future__ import annotations

from dataclasses import dataclass
from math import floor

from app.research.weekly_global_etf_rotation_v1 import UNIVERSE

STRATEGY_VERSION = "monthly-etf-time-series-momentum-whole-share-v4"
LOOKBACK = 252
TREND_DAYS = 200
MAX_EXPOSURE = .95
STOP = .10
ACCOUNT_BREAKER = .20
COOLDOWN_SESSIONS = 63


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
    breaker_events: int


def apply_split(position: tuple[str, int, float, str], factor: int
                ) -> tuple[str, int, float, str]:
    if not isinstance(factor, int) or factor < 1:
        raise ValueError("invalid split factor")
    symbol, shares, entry, entry_day = position
    return symbol, shares * factor, entry / factor, entry_day


def settlement_sessions(day: str) -> int:
    if day < "2017-09-05":
        return 3
    return 2 if day < "2024-05-28" else 1


def evaluate(raw_data: dict[str, list[dict]], signal_data: dict[str, list[dict]],
             *, raw_adjustment: str, signal_adjustment: str,
             split_events: dict[tuple[str, str], int],
             start: str, end: str, cost: float = .001) -> Result:
    if (raw_adjustment != "raw" or signal_adjustment != "split" or
            set(raw_data) != set(UNIVERSE) or set(signal_data) != set(UNIVERSE)):
        raise ValueError("exact universe, raw execution bars, and split-adjusted signal bars required")
    if start >= end or cost < 0:
        raise ValueError("invalid range or cost")
    rows = {s: {str(r["timestamp"])[:10]: r for r in raw_data[s]} for s in UNIVERSE}
    signals = {s: {str(r["timestamp"])[:10]: r for r in signal_data[s]} for s in UNIVERSE}
    dates = sorted(set.intersection(*(set(x) for x in rows.values())))
    if any(set(rows[s]) != set(signals[s]) for s in UNIVERSE):
        raise ValueError("raw and split-adjusted bars must cover identical sessions")
    cash = 100.0
    position: tuple[str, int, float, str] | None = None
    candidates: list[str] = []
    trades: list[Trade] = []
    equity: list[tuple[str, float]] = []
    unavailable = 0
    breaker_events = 0
    account_peak = 100.0
    cooldown_until = -1
    force_exit = False
    month_session = 0
    previous_month = ""
    entry_session = 2
    for i in range(LOOKBACK, len(dates)):
        day = dates[i]
        if day >= end:
            break
        if day < start:
            continue
        month = day[:7]
        if month != previous_month:
            month_session = 1
            entry_session = 1 + settlement_sessions(day)
            previous_month = month
        else:
            month_session += 1
        if i > cooldown_until >= 0:
            account_peak = equity[-1][1] if equity else cash
            cooldown_until = -1
        if position is not None:
            symbol, shares, entry, entry_day = position
            factor = split_events.get((symbol, day), 1)
            if factor != 1:
                position = apply_split(position, factor)
                symbol, shares, entry, entry_day = position
            bar = rows[symbol][day]
            opening, low = float(bar["open"]), float(bar["low"])
            stop = entry * (1 - STOP)
            if force_exit:
                exit_price, reason = opening, "account_breaker"
            elif month_session == 1:
                exit_price, reason = opening, "rebalance"
            elif low <= stop:
                exit_price, reason = min(opening, stop), "stop"
            else:
                exit_price = None
            if exit_price is not None:
                cash += shares * exit_price * (1 - cost / 2)
                trades.append(Trade(symbol, entry_day, day, shares, entry,
                                    exit_price, reason))
                position = None
        force_exit = False
        if month_session == entry_session and position is None and candidates and cooldown_until < i:
            purchased = False
            for symbol in candidates:
                opening = float(rows[symbol][day]["open"])
                shares = floor(min(cash * MAX_EXPOSURE, cash / (1 + cost / 2)) / opening) if opening > 0 else 0
                if shares:
                    cash -= shares * opening * (1 + cost / 2)
                    position = (symbol, shares, opening, day)
                    purchased = True
                    break
            if not purchased:
                unavailable += 1
        if position is not None:
            symbol, shares, entry, entry_day = position
            bar = rows[symbol][day]
            stop = entry * (1 - STOP)
            if float(bar["low"]) <= stop:
                exit_price = min(float(bar["open"]), stop)
                cash += shares * exit_price * (1 - cost / 2)
                trades.append(Trade(symbol, entry_day, day, shares, entry,
                                    exit_price, "stop"))
                position = None
        marked = cash
        if position is not None:
            marked += position[1] * float(rows[position[0]][day]["close"])
        equity.append((day, marked))
        if cooldown_until < i:
            account_peak = max(account_peak, marked)
            if marked <= account_peak * (1 - ACCOUNT_BREAKER):
                breaker_events += 1
                cooldown_until = i + COOLDOWN_SESSIONS
                force_exit = position is not None
        if i + 1 < len(dates) and day[:7] != dates[i + 1][:7]:
            ranked: list[tuple[float, str]] = []
            for symbol in UNIVERSE:
                close = float(signals[symbol][day]["close"])
                prior = float(signals[symbol][dates[i - LOOKBACK]]["close"])
                average = sum(float(signals[symbol][d]["close"])
                              for d in dates[i - TREND_DAYS + 1:i + 1]) / TREND_DAYS
                if prior > 0 and close > prior and close > average:
                    ranked.append((close / prior - 1, symbol))
            candidates = [symbol for _, symbol in sorted(ranked, key=lambda x: (-x[0], x[1]))]
    return Result(trades, equity, unavailable, position is not None,
                  breaker_events)
