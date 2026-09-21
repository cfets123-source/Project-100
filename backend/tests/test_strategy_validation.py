import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.research.strategy_validation import assess_out_of_sample, record_validation, require_passing_validation


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_requires_trade_count_profit_and_drawdown_limit():
    too_few = assess_out_of_sample([.01] * 29)
    assert not too_few.passed
    assert "insufficient out-of-sample trades" in too_few.reasons

    deep_drawdown = assess_out_of_sample([-.20] + [.02] * 30)
    assert not deep_drawdown.passed
    assert "out-of-sample drawdown exceeded threshold" in deep_drawdown.reasons


def test_failed_research_record_blocks_promotion():
    db = _db()
    result = assess_out_of_sample([-.01] * 30)
    record_validation(db, strategy="candidate-v1", result=result)
    with pytest.raises(RuntimeError, match="strategy_validation_failed:candidate-v1"):
        require_passing_validation(db, "candidate-v1")


def test_passing_record_only_applies_to_exact_strategy_version():
    db = _db()
    result = assess_out_of_sample([.01] * 30)
    record_validation(db, strategy="candidate-v1", result=result)
    assert require_passing_validation(db, "candidate-v1").passed
    with pytest.raises(RuntimeError, match="strategy_validation_missing:candidate-v2"):
        require_passing_validation(db, "candidate-v2")
