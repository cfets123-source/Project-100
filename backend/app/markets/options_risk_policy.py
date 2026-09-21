"""Deterministic policy for future long-option research candidates.

This policy cannot construct an order.  It documents the criteria that a
contract must meet before it can even enter an options paper-validation run.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OptionContractObservation:
    bid: float
    ask: float
    delta: float | None
    days_to_expiry: int
    feed: str


@dataclass(frozen=True)
class OptionResearchDecision:
    accepted_for_paper_research: bool
    maximum_debit: float
    reasons: tuple[str, ...]


def evaluate_long_option_candidate(observation: OptionContractObservation, *, account_equity: float) -> OptionResearchDecision:
    """Assess a long option with explicit, bounded loss and data-quality rules.

    A purchased single-leg option's maximum loss is its debit.  The candidate
    is capped at 20% of designated equity but stays research-only until the
    separate strategy, paper lifecycle, and execution gates are completed.
    """
    maximum_debit = round(max(0.0, account_equity) * 0.20, 2)
    reasons: list[str] = []
    if observation.feed != "opra":
        reasons.append("opra_data_required")
    if observation.bid <= 0 or observation.ask <= observation.bid:
        reasons.append("invalid_quote")
    else:
        midpoint = (observation.bid + observation.ask) / 2
        if (observation.ask - observation.bid) / midpoint > 0.10:
            reasons.append("spread_too_wide")
        if observation.ask * 100 > maximum_debit:
            reasons.append("debit_exceeds_research_budget")
    if observation.delta is None or not 0.30 <= abs(observation.delta) <= 0.70:
        reasons.append("delta_outside_range")
    if not 14 <= observation.days_to_expiry <= 45:
        reasons.append("expiry_outside_range")
    return OptionResearchDecision(not reasons, maximum_debit, tuple(reasons))
