from types import SimpleNamespace
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.session import Base
from app.models.models import TradeDecisionRecord, OrderIntent, CapitalStageState, SystemStateRecord
from app.analytics.performance import summarize, account_performance
from app.services.capital_stages import StagePolicy, evaluate_paper_stage


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_trades(db, pnls=(-1,3,3,3,3), account='paper-1'):
    for pnl in pnls:
        uid = str(uuid.uuid4())
        db.add(TradeDecisionRecord(trade_id=uid, strategy='test-strategy', symbol='TST',
                                   status='closed', pnl=pnl, r_multiple=pnl))
        db.add(OrderIntent(intent_key=uid, trade_id=uid, decision_id=uid, account_id=account, status='filled'))
    db.commit()


def policy(**kwargs):
    return StagePolicy(minimum_trades=5, minimum_losses=1, **kwargs)


def test_metrics_handle_empty_and_zero_losses_without_infinity():
    assert summarize([])['expectancy'] is None
    result = summarize([SimpleNamespace(pnl=2,r_multiple=2)] * 3)
    assert result['profit_factor'] is None
    assert result['trade_sharpe_like'] is None
    assert result['sample_size'] == 3


def test_metrics_reject_incomplete_closed_ledger():
    with pytest.raises(ValueError):
        summarize([SimpleNamespace(pnl=None, r_multiple=1)])


def test_account_performance_does_not_mix_other_accounts(db):
    add_trades(db)
    add_trades(db, [100000], account='different-account')
    result = account_performance(db)
    assert result['overall']['sample_size'] == 5
    assert result['overall']['realized_pnl'] == 11
    assert result['simulated']


def test_capital_alone_cannot_graduate(db):
    result = evaluate_paper_stage(db, 1000000, 0, True, policy())
    assert result['index'] == 0
    assert 'insufficient_trade_sample' in result['reasons']


def test_gradual_promotion_requires_new_sample_for_every_stage(db):
    add_trades(db)
    result = evaluate_paper_stage(db, 1000000, .01, True, policy())
    assert result['index'] == 1 and result['last_action'] == 'graduate'
    repeat = evaluate_paper_stage(db, 1000000, .01, True, policy())
    assert repeat['index'] == 1
    assert 'insufficient_trade_sample' in repeat['reasons']
    add_trades(db)
    assert evaluate_paper_stage(db, 1000000, .01, True, policy())['index'] == 2
    assert db.query(SystemStateRecord).count() == 0  # no execution permission writes


@pytest.mark.parametrize('healthy,drawdown', [(False,0), (True,.2)])
def test_health_and_drawdown_block_graduation(db, healthy, drawdown):
    add_trades(db)
    assert evaluate_paper_stage(db, 1000, drawdown, healthy, policy())['index'] == 0


def test_unresolved_order_blocks_graduation(db):
    add_trades(db)
    db.add(OrderIntent(intent_key='unknown', account_id='paper-1', status='unknown'))
    db.commit()
    result = evaluate_paper_stage(db, 1000, 0, True, policy())
    assert 'unresolved_system_or_order_issue' in result['reasons']
    assert result['index'] == 0


def test_capital_retracement_demotes_without_risk_escalation(db):
    add_trades(db)
    evaluate_paper_stage(db, 1000, 0, True, policy())
    result = evaluate_paper_stage(db, 900, .05, True, policy())
    assert result['index'] == 0 and result['last_action'] == 'demote'
    assert result['risk_configuration_changed'] is False


def test_stage_policy_cannot_change_silently(db):
    evaluate_paper_stage(db, 100, 0, True, policy())
    with pytest.raises(ValueError):
        evaluate_paper_stage(db, 100, 0, True, StagePolicy(minimum_trades=3, minimum_losses=1))


def test_intermediate_300k_is_optional_extra_checkpoint():
    assert StagePolicy().milestones == [1000,10000,100000,500000,1000000]
    assert StagePolicy(intermediate_milestone=300000).milestones == [1000,10000,100000,300000,500000,1000000]
    assert StagePolicy(opening_milestone=500).milestones == [500,1000,10000,100000,500000,1000000]


def test_500_waypoint_is_explicit_and_old_policy_remains_compatible(db):
    row = CapitalStageState(id='paper:paper-1', payload={'index': 0, 'used_trade_ids': [],
        'policy': StagePolicy(minimum_trades=5, minimum_losses=1).model_dump(exclude={'opening_milestone'}),
        'last_action': 'hold', 'reasons': ['insufficient_history']})
    db.add(row)
    db.commit()
    result = evaluate_paper_stage(db, 100, 0, True, policy())
    assert result['next_milestone'] == 1000
    with pytest.raises(ValueError):
        evaluate_paper_stage(db, 100, 0, True, policy(opening_milestone=500))


def test_new_paper_stage_can_track_500_before_1000(db):
    result = evaluate_paper_stage(db, 100, 0, True, policy(opening_milestone=500))
    assert result['next_milestone'] == 500
    assert result['index'] == 0


def test_stage_state_survives_a_new_session(db):
    add_trades(db)
    evaluate_paper_stage(db, 1000, 0, True, policy())
    with Session(db.get_bind()) as restarted:
        assert restarted.get(CapitalStageState, 'paper:paper-1').payload['index'] == 1


def test_late_closing_trade_is_not_skipped_by_entry_order(db):
    import datetime as dt
    add_trades(db)
    evaluate_paper_stage(db, 1000, 0, True, policy())
    uid = 'late-close'
    db.add(TradeDecisionRecord(trade_id=uid, timestamp=dt.datetime(2000,1,1), strategy='test',
                               status='closed', pnl=2, r_multiple=2))
    db.add(OrderIntent(intent_key=uid, trade_id=uid, decision_id=uid, account_id='paper-1', status='filled'))
    db.commit()
    result = evaluate_paper_stage(db, 10000, 0, True, policy())
    assert result['evaluation_metrics']['sample_size'] == 1
