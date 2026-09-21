"""Read-only multi-asset research scanner.

This scanner has no broker mutation path.  It accepts only a capability report
and completed market observations, then records ranked candidates or explicit
rejection reasons for the operator and research pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from app.markets.capabilities import AssetClass, CapabilityRegistry


@dataclass(frozen=True)
class ScanCandidate:
    symbol: str
    asset_class: AssetClass
    score: float
    status: str
    reason: str


def rank_research_candidates(observations: list[dict], registry: CapabilityRegistry | None = None) -> list[dict]:
    """Rank fresh, liquid observations; never grants execution authority."""
    registry = registry or CapabilityRegistry()
    ranked: list[ScanCandidate] = []
    for item in observations:
        asset_class = AssetClass(item["asset_class"])
        fresh = bool(item.get("market_data_ready"))
        liquid = float(item.get("avg_dollar_volume", 0)) >= 1_000_000
        # A scanner can surface a research candidate when broker/data support
        # exists.  The registry retains the execution boundary separately.
        capability = next(entry for entry in registry.report() if entry["asset_class"] == asset_class)
        if not capability["broker_supported"]:
            ranked.append(ScanCandidate(item["symbol"], asset_class, 0, "blocked", "broker_not_supported")); continue
        if not fresh:
            ranked.append(ScanCandidate(item["symbol"], asset_class, 0, "blocked", "market_data_not_available")); continue
        if not liquid:
            ranked.append(ScanCandidate(item["symbol"], asset_class, 0, "blocked", "insufficient_liquidity")); continue
        score = float(item.get("trend_score", 0)) + float(item.get("momentum_score", 0))
        ranked.append(ScanCandidate(item["symbol"], asset_class, score, "research_candidate", "research_only"))
    return [asdict(row) for row in sorted(ranked, key=lambda row: row.score, reverse=True)]
