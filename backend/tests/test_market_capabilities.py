from app.markets.capabilities import AssetClass, CapabilityRegistry


def test_options_remain_blocked_until_every_promotion_gate_passes():
    registry = CapabilityRegistry()
    assert registry.eligible(AssetClass.US_OPTION, account_approved=False, market_data_ready=True,
                             strategy_validated=True, paper_lifecycle_passed=True, live_gate=True) == (False, "account_approval_required")
    assert registry.eligible(AssetClass.US_OPTION, account_approved=True, market_data_ready=True,
                             strategy_validated=True, paper_lifecycle_passed=True, live_gate=True) == (False, "live_capability_disabled")


def test_equities_require_evidence_before_live_eligibility():
    registry = CapabilityRegistry()
    assert registry.eligible(AssetClass.US_EQUITY, account_approved=True, market_data_ready=True,
                             strategy_validated=False, paper_lifecycle_passed=True, live_gate=True) == (False, "strategy_validation_required")
