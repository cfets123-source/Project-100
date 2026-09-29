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


def test_execution_evidence_requires_same_contract_and_validation_run():
    from app.runtime.alpaca_live_execution import (
        DAILY_PULLBACK_EXECUTION_CONTRACT, require_execution_validation)
    from app.models.models import StrategyValidationRecord
    db = _db()
    strategy = 'daily-trend-pullback-portfolio-v1'
    passing = assess_out_of_sample([.01] * 30)
    record_validation(db, strategy=strategy, result=passing)
    with pytest.raises(RuntimeError, match='execution_contract_mismatch'):
        require_execution_validation(db, strategy)
    record_validation(db, strategy=strategy, result=passing, execution_contract='overnight-v1')
    with pytest.raises(RuntimeError, match='execution_contract_mismatch'):
        require_execution_validation(db, strategy)
    record_validation(db, strategy=strategy, result=passing,
                      execution_contract=DAILY_PULLBACK_EXECUTION_CONTRACT)
    assert require_execution_validation(db, strategy).passed
    # An independent rewrite of validation cannot reuse old execution evidence.
    import datetime as dt
    db.get(StrategyValidationRecord, strategy).evaluated_at += dt.timedelta(seconds=1)
    db.commit()
    with pytest.raises(RuntimeError, match='execution_contract_mismatch'):
        require_execution_validation(db, strategy)


def test_rerun_revokes_contract_and_failed_matched_run_still_blocks():
    db = _db()
    passing = assess_out_of_sample([.01] * 30)
    record_validation(db, strategy='candidate', result=passing, execution_contract='matched-v1')
    record_validation(db, strategy='candidate', result=passing)
    with pytest.raises(RuntimeError, match='execution_contract_mismatch'):
        require_passing_validation(db, 'candidate', execution_contract='matched-v1')
    record_validation(db, strategy='candidate', result=assess_out_of_sample([-.01] * 30),
                      execution_contract='matched-v1')
    with pytest.raises(RuntimeError, match='strategy_validation_failed'):
        require_passing_validation(db, 'candidate', execution_contract='matched-v1')


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf'), -1.01])
def test_invalid_account_returns_cannot_pass(bad):
    with pytest.raises(ValueError, match='account returns'):
        assess_out_of_sample([bad] * 30)


@pytest.mark.parametrize('kwargs', [dict(minimum_trades=0), dict(max_drawdown=float('nan')),
                                    dict(max_drawdown=1.1), dict(minimum_return=float('nan'))])
def test_invalid_validation_thresholds_are_rejected(kwargs):
    with pytest.raises(ValueError, match='thresholds'):
        assess_out_of_sample([.01] * 30, **kwargs)


def test_total_loss_cannot_recover_through_compounding():
    result = assess_out_of_sample([-1.] + [.1] * 30)
    assert result.total_return == -1
    assert not result.passed


def test_invalid_result_cannot_overwrite_existing_evidence():
    from dataclasses import replace
    db = _db()
    passing = assess_out_of_sample([.01] * 30)
    record_validation(db, strategy='candidate', result=passing)
    with pytest.raises(ValueError, match='invalid validation result'):
        record_validation(db, strategy='candidate', result=replace(passing, total_return=float('nan')))
    assert require_passing_validation(db, 'candidate').total_return == passing.total_return
