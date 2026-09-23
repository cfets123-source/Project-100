"""Bounded development-only factor screen for whole-share cash accounts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor

from app.research.weekly_affordable_momentum_v1 import UNIVERSE

RULES = tuple((style, lookback, trend)
              for style, lookbacks in (("momentum", (20, 63, 126)),
                                         ("reversal", (5, 20)))
              for lookback in lookbacks for trend in (False, True))


@dataclass(frozen=True)
class ScreenResult:
    rule: str
    trades: int
    return_pct: float
    drawdown_pct: float
    equity: tuple[tuple[str, float], ...]


def rule_name(style: str, lookback: int, trend: bool) -> str:
    return f"{style}-{lookback}-{'trend' if trend else 'all'}"


def evaluate(data: dict[str, list[dict]], *, adjustment: str,
             style: str, lookback: int, trend: bool,
             start: str = "2022-01-01", end: str = "2025-01-01",
             cost: float = .001) -> ScreenResult:
    if adjustment != "raw" or set(data) != set(UNIVERSE):
        raise ValueError("exact fixed universe with raw prices required")
    if (style, lookback, trend) not in RULES:
        raise ValueError("rule is outside the frozen factor screen")
    if cost < 0 or start >= end:
        raise ValueError("invalid cost or date range")
    by_symbol = {s: {str(x["timestamp"])[:10]: x for x in data[s]}
                 for s in UNIVERSE}
    dates = sorted(set.intersection(*(set(x) for x in by_symbol.values())))
    cash = 100.0
    position: tuple[str, int, float, int] | None = None
    pending: list[str] = []
    completed = 0
    values: list[tuple[str, float]] = []
    warmup = max(100, lookback)
    for i in range(warmup, len(dates)):
        day = dates[i]
        if day >= end:
            break
        if day < start:
            continue
        exited = False
        if position is None and pending:
            for symbol in pending:
                opening = float(by_symbol[symbol][day]["open"])
                shares = floor(min(cash / (1 + cost / 2), cash * .9) / opening) if opening > 0 else 0
                if shares:
                    cash -= shares * opening * (1 + cost / 2)
                    position = symbol, shares, opening, 0
                    break
        pending = []
        if position is not None:
            symbol, shares, entry, held = position
            bar = by_symbol[symbol][day]
            opening, low, high, close = (float(bar[k]) for k in ("open", "low", "high", "close"))
            stop, target = entry * .95, entry * 1.1
            if low <= stop:
                exit_price = min(opening, stop)
            elif high >= target:
                exit_price = target
            elif held + 1 >= 10:
                exit_price = close
            else:
                exit_price = None
            if exit_price is not None:
                cash += shares * exit_price * (1 - cost / 2)
                position = None
                completed += 1
                exited = True
            else:
                position = symbol, shares, entry, held + 1
        mark = cash
        if position is not None:
            mark += position[1] * float(by_symbol[position[0]][day]["close"])
        values.append((day, mark))
        if position is not None or exited or date.fromisoformat(day).weekday() != 4:
            continue
        candidates: list[tuple[float, str]] = []
        for symbol in UNIVERSE:
            series = by_symbol[symbol]
            current = float(series[day]["close"])
            prior = float(series[dates[i - lookback]]["close"])
            if current <= 0 or prior <= 0:
                continue
            ret = current / prior - 1
            if style == "momentum" and ret <= 0 or style == "reversal" and ret >= 0:
                continue
            if trend:
                average = sum(float(series[d]["close"]) for d in dates[i - 99:i + 1]) / 100
                if current <= average:
                    continue
            candidates.append((ret, symbol))
        if style == "momentum":
            candidates.sort(key=lambda x: (-x[0], x[1]))
        else:
            candidates.sort(key=lambda x: (x[0], x[1]))
        pending = [symbol for _, symbol in candidates]
    peak = 100.0
    drawdown = 0.0
    for _, value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    return ScreenResult(rule_name(style, lookback, trend), completed,
                        (values[-1][1] / 100 - 1) if values else 0.0,
                        drawdown, tuple(values))


def select_development(results: list[ScreenResult]) -> ScreenResult | None:
    eligible = [r for r in results if r.trades >= 25 and r.return_pct > 0
                and r.drawdown_pct > -.25]
    return max(eligible, key=lambda r: (r.return_pct / (1 + 3 * abs(r.drawdown_pct)),
                                       r.rule)) if eligible else None
