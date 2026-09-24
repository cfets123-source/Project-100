"""Recovery-aware account-path assessment; no single losing day is a veto."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RecoveryPath:
    days: int
    end_equity: float
    target_day: int | None
    worst_drawdown: float
    longest_underwater_days: int
    longest_loss_streak: int
    worst_drawdown_recovery_days: int | None
    remaining_recovery_pct: float
    floor_crossed: bool


def assess_recovery_path(
    daily_returns: list[float], *, start_equity: float,
    target_equity: float, floor_equity: float = 0.0,
) -> RecoveryPath:
    """Measure milestone progress and the cost of recovering from losses.

    Returns include idle days and all execution costs. The path continues
    after a target touch so a later collapse is visible.
    """
    if (
        not daily_returns or not math.isfinite(start_equity)
        or not math.isfinite(target_equity) or not math.isfinite(floor_equity)
        or start_equity <= 0 or target_equity <= start_equity
        or floor_equity < 0 or floor_equity >= start_equity
        or any(not math.isfinite(r) or r < -1 for r in daily_returns)
    ):
        raise ValueError("invalid account path")
    equity = peak = start_equity
    target_day = None
    worst_drawdown = 0.0
    worst_recovery_peak = start_equity
    worst_recovery_start = None
    worst_recovery_days = None
    underwater = longest_underwater = 0
    losses = longest_losses = 0
    crossed_floor = False
    for day, value in enumerate(daily_returns, 1):
        equity *= 1 + value
        crossed_floor |= equity <= floor_equity
        if target_day is None and equity >= target_equity:
            target_day = day
        losses = losses + 1 if value < 0 else 0
        longest_losses = max(longest_losses, losses)
        if equity >= peak:
            peak = equity
            underwater = 0
        else:
            underwater += 1
            longest_underwater = max(longest_underwater, underwater)
        drawdown = 1 - equity / peak if peak else 1
        if drawdown > worst_drawdown:
            worst_drawdown = drawdown
            worst_recovery_peak = peak
            worst_recovery_start = day
            worst_recovery_days = None
        elif (
            worst_recovery_start is not None
            and worst_recovery_days is None
            and equity >= worst_recovery_peak
        ):
            worst_recovery_days = day - worst_recovery_start
    return RecoveryPath(
        days=len(daily_returns), end_equity=equity, target_day=target_day,
        worst_drawdown=worst_drawdown,
        longest_underwater_days=longest_underwater,
        longest_loss_streak=longest_losses,
        worst_drawdown_recovery_days=worst_recovery_days,
        remaining_recovery_pct=(peak / equity - 1) if equity > 0 else math.inf,
        floor_crossed=crossed_floor,
    )
