"""Explicit asset-class capability and promotion policy.

Scanners must consult this registry before returning a candidate.  It prevents
an available symbol, quote, or broker endpoint from being mistaken for live
trading authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class AssetClass(str, Enum):
    US_EQUITY = "us_equity"
    ETF = "etf"
    CRYPTO = "crypto"
    US_OPTION = "us_option"


@dataclass(frozen=True)
class Capability:
    asset_class: AssetClass
    broker_supported: bool
    requires_account_approval: bool
    requires_market_data: bool
    paper_enabled: bool = False
    live_enabled: bool = False
    reason: str = ""


class CapabilityRegistry:
    def __init__(self, entries: list[Capability] | None = None):
        self._entries = {entry.asset_class: entry for entry in entries or default_capabilities()}

    def report(self) -> list[dict]:
        return [asdict(self._entries[key]) for key in AssetClass]

    def eligible(self, asset_class: AssetClass, *, account_approved: bool,
                 market_data_ready: bool, strategy_validated: bool,
                 paper_lifecycle_passed: bool, live_gate: bool) -> tuple[bool, str]:
        cap = self._entries[asset_class]
        if not cap.broker_supported:
            return False, "broker_not_supported"
        if cap.requires_account_approval and not account_approved:
            return False, "account_approval_required"
        if cap.requires_market_data and not market_data_ready:
            return False, "market_data_not_available"
        if not strategy_validated:
            return False, "strategy_validation_required"
        if not paper_lifecycle_passed:
            return False, "paper_lifecycle_required"
        if not cap.live_enabled or not live_gate:
            return False, "live_capability_disabled"
        return True, "eligible"


def default_capabilities() -> list[Capability]:
    return [
        Capability(AssetClass.US_EQUITY, True, False, True, paper_enabled=True, live_enabled=True,
                   reason="current designated-account execution path"),
        Capability(AssetClass.ETF, True, False, True, paper_enabled=True, live_enabled=True,
                   reason="current designated-account execution path"),
        Capability(AssetClass.CRYPTO, True, True, True,
                   reason="requires a separately enabled Alpaca crypto agreement, data check, validation, and paper lifecycle"),
        Capability(AssetClass.US_OPTION, True, True, True,
                   reason="requires broker approval, options data, dedicated strategy validation, and paper lifecycle"),
    ]
