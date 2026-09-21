"""Research-only, risk-on momentum-breakout hypothesis.

This candidate differs from the initial breakout test by specifying its risk
policy before validation: it participates only in a broad risk-on regime,
targets a fixed portfolio volatility without leverage, and pauses after a
material peak-to-trough loss.  It is not a live strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import stdev

from app.research.liquid_momentum_breakout import (
    BREAKOUT_DAYS, MAX_HOLD_DAYS, ROUND_TRIP_COST, STOP_LOSS, TAKE_PROFIT,
    UNIVERSE, WARMUP_BARS, _aligned,
)


STRATEGY_VERSION = "regime-liquid-momentum-breakout-v1"
REGIME_DAYS = 200
TARGET_ANNUALIZED_TRADE_VOL = 0.16
TRAILING_TRADES = 12
TRADES_PER_YEAR = 30
MAX_PORTFOLIO_DRAWDOWN = 0.10


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_timestamp: str
    exit_timestamp: str
    raw_return: float
    applied_return: float
    exit_reason: str
    exposure: float


def _exposure(closed_returns: list[float], equity: float, peak: float) -> float:
    """Fixed, non-levered volatility target with a drawdown pause."""
    if equity < peak * (1 - MAX_PORTFOLIO_DRAWDOWN):
        return 0.0
    trailing = closed_returns[-TRAILING_TRADES:]
    if len(trailing) < 4:
        return 1.0
    annualized_vol = stdev(trailing) * sqrt(TRADES_PER_YEAR)
    return min(1.0, TARGET_ANNUALIZED_TRADE_VOL / annualized_vol) if annualized_vol else 1.0


def evaluate(data: dict[str, list[dict]], *, split: str,
             symbols: tuple[str, ...] = UNIVERSE) -> list[Trade]:
    """One-position chronological research portfolio with no look-ahead."""
    if set(data) != set(symbols):
        raise ValueError("data must contain exactly the liquid momentum universe")
    dates, indexed = _aligned(data)
    if len(dates) <= REGIME_DAYS + MAX_HOLD_DAYS + 1:
        return []
    trades: list[Trade] = []
    closed_returns: list[float] = []
    equity = peak = 1.0
    open_trade: tuple[str, float, float, float, int, str, float] | None = None
    for index in range(max(WARMUP_BARS, REGIME_DAYS), len(dates) - 1):
        date = dates[index]
        if open_trade is not None:
            symbol, entry, stop, target, entry_index, entry_timestamp, exposure = open_trade
            row = indexed[symbol][date]
            if float(row["low"]) <= stop:
                exit_price, reason = stop, "stop"
            elif float(row["high"]) >= target:
                exit_price, reason = target, "target"
            elif index - entry_index >= MAX_HOLD_DAYS:
                exit_price, reason = float(row["close"]), "time_exit"
            else:
                continue
            raw = exit_price / entry - 1.0 - ROUND_TRIP_COST
            applied = raw * exposure
            trades.append(Trade(symbol, entry_timestamp, date, raw, applied, reason, exposure))
            closed_returns.append(applied)
            equity *= 1.0 + applied
            peak = max(peak, equity)
            open_trade = None
            continue

        if date < split or _exposure(closed_returns, equity, peak) <= 0:
            continue
        spy_rows = [indexed["SPY"][item] for item in dates[index - REGIME_DAYS + 1:index + 1]]
        spy_close = float(spy_rows[-1]["close"])
        if spy_close <= sum(float(row["close"]) for row in spy_rows) / REGIME_DAYS:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol in symbols:
            rows = [indexed[symbol][item] for item in dates[index - WARMUP_BARS:index + 1]]
            close = float(rows[-1]["close"])
            sma50 = sum(float(row["close"]) for row in rows[-50:]) / 50
            prior_high = max(float(row["high"]) for row in rows[-BREAKOUT_DAYS - 1:-1])
            momentum = close / float(rows[-21]["close"]) - 1.0
            average_volume = sum(float(row["volume"]) for row in rows[-21:-1]) / 20
            volume_ratio = float(rows[-1]["volume"]) / average_volume if average_volume else 0.0
            if close > sma50 and close >= prior_high and momentum >= 0.03 and volume_ratio >= 1.0:
                candidates.append((momentum + 0.05 * (volume_ratio - 1.0), symbol))
        if candidates:
            _, symbol = max(candidates)
            entry = float(indexed[symbol][dates[index + 1]]["open"])
            open_trade = (symbol, entry, entry * (1 - STOP_LOSS), entry * (1 + TAKE_PROFIT),
                          index + 1, dates[index + 1], _exposure(closed_returns, equity, peak))
    return trades
