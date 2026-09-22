"""Comparable, all-in economics for a proposed broker venue.

Callers must supply an independently estimated gross edge and current venue
costs. Unknown fees or data cost are a veto, not a zero-cost assumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class VenueEstimate:
    venue: str
    notional: Decimal
    expected_gross_profit: Decimal | None
    entry_commission: Decimal | None
    exit_commission: Decimal | None
    round_trip_spread_bps: Decimal | None
    round_trip_slippage_bps: Decimal | None
    round_trip_fx_bps: Decimal | None = Decimal("0")
    allocated_data_cost: Decimal | None = None


@dataclass(frozen=True)
class VenueEconomics:
    venue: str
    eligible: bool
    reason: str
    all_in_cost: Decimal | None
    expected_net_profit: Decimal | None
    cost_pct: Decimal | None
    expected_net_return_pct: Decimal | None


def evaluate_venue(estimate: VenueEstimate) -> VenueEconomics:
    values = (estimate.expected_gross_profit, estimate.entry_commission,
              estimate.exit_commission, estimate.round_trip_spread_bps,
              estimate.round_trip_slippage_bps, estimate.round_trip_fx_bps,
              estimate.allocated_data_cost)
    if (not estimate.notional.is_finite() or estimate.notional <= 0
            or any(v is None or not v.is_finite() or v < 0 for v in values)):
        return VenueEconomics(estimate.venue, False, "cost_or_edge_unknown", None, None, None, None)
    variable_bps = (estimate.round_trip_spread_bps + estimate.round_trip_slippage_bps
                    + estimate.round_trip_fx_bps)
    all_in = (estimate.entry_commission + estimate.exit_commission
              + estimate.allocated_data_cost + estimate.notional * variable_bps / Decimal("10000"))
    net = estimate.expected_gross_profit - all_in
    return VenueEconomics(estimate.venue, net > 0,
                          "positive_net_edge" if net > 0 else "cost_exceeds_expected_edge",
                          all_in, net, all_in / estimate.notional * Decimal("100"),
                          net / estimate.notional * Decimal("100"))


def select_venue(estimates: list[VenueEstimate]) -> VenueEconomics | None:
    """Choose the highest positive net edge, irrespective of headline commission."""
    if len({item.notional for item in estimates}) > 1:
        return None  # Different trade sizes do not have comparable net dollars.
    eligible = [result for item in estimates if (result := evaluate_venue(item)).eligible]
    return max(eligible, key=lambda result: (result.expected_net_profit, result.venue)) if eligible else None
