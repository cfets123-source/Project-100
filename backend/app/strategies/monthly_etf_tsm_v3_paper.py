"""Exact-version paper entry planner; calculations never submit an order."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from math import floor, isfinite

from app.brokers.base import OrderRequest
from app.research.monthly_etf_time_series_momentum_v3 import (
    LOOKBACK, MAX_EXPOSURE, STOP, STRATEGY_VERSION, TREND_DAYS, UNIVERSE,
)


@dataclass(frozen=True)
class PaperPlan:
    strategy: str
    asof_day: str
    signal_day: str | None
    ranked_symbols: tuple[str, ...]
    reason: str


def entry_plan(raw_data: dict[str, list[dict]], signal_data: dict[str, list[dict]],
               *, raw_adjustment: str, signal_adjustment: str,
               asof_day: str, session_days: list[str]) -> PaperPlan:
    if (raw_adjustment != "raw" or signal_adjustment != "split" or
            set(raw_data) != set(UNIVERSE) or set(signal_data) != set(UNIVERSE)):
        raise ValueError("paper planner requires exact ETF universe, raw and split-adjusted bars")
    sessions = sorted(set(session_days))
    if asof_day not in sessions or len([day for day in sessions
                                        if day[:7] == asof_day[:7] and day <= asof_day]) != 2:
        return PaperPlan(STRATEGY_VERSION, asof_day, None, (),
                         "not_second_trading_session")
    rows = {s: {str(row["timestamp"])[:10]: row for row in raw_data[s]
                if str(row["timestamp"])[:10] < asof_day}
            for s in UNIVERSE}
    signals = {s: {str(row["timestamp"])[:10]: row for row in signal_data[s]
                   if str(row["timestamp"])[:10] < asof_day}
               for s in UNIVERSE}
    if any(set(rows[s]) != set(signals[s]) for s in UNIVERSE):
        return PaperPlan(STRATEGY_VERSION, asof_day, None, (),
                         "raw_signal_session_mismatch")
    # A discontinuity remaining in split-adjusted bars means an unresolved
    # corporate action, bad feed, or exceptional move requiring manual review.
    for symbol in UNIVERSE:
        previous = None
        for day in sorted(signals[symbol]):
            close = float(signals[symbol][day]["close"])
            if not isfinite(close) or close <= 0 or (previous and
                    (close / previous < .70 or close / previous > 1.40)):
                return PaperPlan(STRATEGY_VERSION, asof_day, None, (),
                                 "unresolved_signal_price_discontinuity")
            previous = close
    dates = sorted(set.intersection(*(set(series) for series in rows.values())))
    first_session = next(day for day in sessions if day[:7] == asof_day[:7])
    if first_session not in dates:
        return PaperPlan(STRATEGY_VERSION, asof_day, None, (),
                         "missing_first_session_bars")
    prior = [day for day in sessions if day < first_session]
    if not prior or prior[-1] not in dates:
        return PaperPlan(STRATEGY_VERSION, asof_day, None, (),
                         "missing_prior_month_close")
    signal_day = prior[-1]
    index = dates.index(signal_day)
    if index < LOOKBACK:
        return PaperPlan(STRATEGY_VERSION, asof_day, signal_day, (),
                         "insufficient_indicator_history")
    ranked: list[tuple[float, str]] = []
    for symbol in UNIVERSE:
        current = float(signals[symbol][signal_day]["close"])
        past = float(signals[symbol][dates[index - LOOKBACK]]["close"])
        average = sum(float(signals[symbol][day]["close"])
                      for day in dates[index - TREND_DAYS + 1:index + 1]) / TREND_DAYS
        if all(isfinite(value) and value > 0 for value in (past, current, average)) and current > past and current > average:
            ranked.append((current / past - 1, symbol))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return PaperPlan(STRATEGY_VERSION, asof_day, signal_day,
                     tuple(symbol for _, symbol in ranked),
                     "eligible" if ranked else "hold_cash")


def entry_order(plan: PaperPlan, *, asks: dict[str, float], tradable: set[str],
                settled_cash: float, capital_cap: float = 100.0) -> OrderRequest | None:
    if plan.strategy != STRATEGY_VERSION or plan.reason != "eligible":
        return None
    budget = min(max(0.0, settled_cash), max(0.0, capital_cap)) * MAX_EXPOSURE
    for symbol in plan.ranked_symbols:
        if symbol not in tradable:
            continue
        ask = float(asks.get(symbol) or 0)
        if not isfinite(ask) or ask <= 0:
            continue
        quantity = floor(budget / ask)
        if quantity < 1:
            continue
        stop = float((Decimal(str(ask)) * Decimal(str(1 - STOP)))
                     .quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        return OrderRequest(symbol=symbol, side="buy", quantity=quantity,
                            order_type="market", time_in_force="gtc",
                            order_class="oto", stop_loss_price=stop,
                            client_order_id=f"p100-etf-{plan.asof_day[:7].replace('-', '')}-{symbol}")
    return None
