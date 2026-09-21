from app.markets.options_risk_policy import OptionContractObservation, evaluate_long_option_candidate


def test_qualified_contract_is_research_only_candidate_not_execution_signal():
    decision = evaluate_long_option_candidate(
        OptionContractObservation(bid=0.12, ask=0.13, delta=0.45, days_to_expiry=21, feed="opra"),
        account_equity=100,
    )
    assert decision.accepted_for_paper_research is True
    assert decision.maximum_debit == 20.0


def test_indicative_feed_and_expensive_contract_are_rejected():
    decision = evaluate_long_option_candidate(
        OptionContractObservation(bid=0.50, ask=0.55, delta=0.45, days_to_expiry=21, feed="indicative"),
        account_equity=100,
    )
    assert decision.accepted_for_paper_research is False
    assert set(decision.reasons) == {"opra_data_required", "debit_exceeds_research_budget"}


def test_expiry_and_delta_rules_are_enforced():
    decision = evaluate_long_option_candidate(
        OptionContractObservation(bid=0.10, ask=0.11, delta=0.10, days_to_expiry=4, feed="opra"),
        account_equity=100,
    )
    assert decision.accepted_for_paper_research is False
    assert set(decision.reasons) == {"delta_outside_range", "expiry_outside_range"}
