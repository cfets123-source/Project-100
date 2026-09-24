from app.research.run_defensive_rotation_validation import EXECUTION_MISMATCH, promotion_result
from app.research.strategy_validation import ValidationResult


def test_positive_research_return_cannot_promote_mismatched_execution():
    research = ValidationResult(43, .6, .304, -.09, True, [])
    promotion = promotion_result(research)
    assert promotion.total_return == research.total_return
    assert promotion.trades == research.trades
    assert not promotion.passed
    assert promotion.reasons == [EXECUTION_MISMATCH]
