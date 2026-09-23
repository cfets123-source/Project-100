"""Descriptive milestone stress test for a frozen, net-of-cost daily return path.

Resampled frequencies describe the supplied history; they are not forecasts or
permission to trade. Flat days belong in the input because time is part of the
milestone objective. Fixed-length blocks retain short runs of wins and losses.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class StageDistribution:
    observed_days: int
    observed_end: float
    observed_target_day: int | None
    observed_max_drawdown: float
    sampled_paths: int
    target_fraction: float
    floor_fraction: float
    ending_equity_p10: float
    ending_equity_p50: float
    ending_equity_p90: float


def _path(returns: list[float], start: float, target: float,
          floor: float) -> tuple[float, int | None, float, bool]:
    equity = peak = start
    worst_drawdown = 0.0
    crossed_floor = False
    for day, daily_return in enumerate(returns, 1):
        equity *= 1.0 + daily_return
        peak = max(peak, equity)
        worst_drawdown = max(worst_drawdown, 1.0 - equity / peak)
        crossed_floor |= equity <= floor
        if equity >= target:
            return equity, day, worst_drawdown, crossed_floor
    return equity, None, worst_drawdown, crossed_floor


def assess_stage_distribution(daily_returns: list[float], *, start_equity: float,
                              target_equity: float, horizon_days: int,
                              floor_fraction_of_start: float = 0.5,
                              block_days: int = 5, paths: int = 2000,
                              seed: int = 0) -> StageDistribution:
    """Resample contiguous daily blocks; stop each path on its milestone hit."""
    if (len(daily_returns) < 60 or horizon_days < 1
            or len(daily_returns) < horizon_days or block_days < 1
            or paths < 100 or not math.isfinite(start_equity)
            or not math.isfinite(target_equity) or start_equity <= 0
            or target_equity <= start_equity
            or not math.isfinite(floor_fraction_of_start)
            or not 0 < floor_fraction_of_start < 1
            or any(not math.isfinite(value) or value <= -1 for value in daily_returns)):
        raise ValueError("invalid or insufficient stage return history")
    floor = start_equity * floor_fraction_of_start
    observed_end, observed_day, observed_drawdown, _ = _path(
        daily_returns[:horizon_days], start_equity, target_equity, floor)
    rng = random.Random(seed)
    n = len(daily_returns)
    endings: list[float] = []
    hits = floors = 0
    for _ in range(paths):
        sampled: list[float] = []
        while len(sampled) < horizon_days:
            first = rng.randrange(n)
            sampled.extend(daily_returns[(first + j) % n] for j in range(block_days))
        ending, day, _, crossed_floor = _path(sampled[:horizon_days],
                                               start_equity, target_equity, floor)
        endings.append(ending)
        hits += day is not None
        floors += crossed_floor
    endings.sort()
    def percentile(p: float) -> float:
        return endings[int((paths - 1) * p)]
    return StageDistribution(len(daily_returns), observed_end, observed_day,
                             observed_drawdown, paths, hits / paths, floors / paths,
                             percentile(.1), percentile(.5), percentile(.9))
