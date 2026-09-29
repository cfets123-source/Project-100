from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest
from app.db.session import Base
from app.services.milestone_lifecycle import MilestonePolicy, StageSnapshot, advance_stage, read_stage

@pytest.fixture
def db():
    e=create_engine('sqlite:///:memory:');Base.metadata.create_all(e)
    with Session(e) as s: yield s

def snapshot(i=1, **kw):
    values=dict(observation_id=str(i),observed_at=1000+i,account_id='account',mode='paper',equity=210,
                cash=10,available_cash=10,cumulative_external_flows=100,open_positions=1,
                active_orders=0,unresolved_intents=0,reconciled=True)
    values.update(kw);return StageSnapshot(**values)

def test_sell_reconcile_then_next_stage_survives_restart(db):
    s=advance_stage(db,snapshot()); assert s['action']=='request_liquidation'; assert s['achieved']==[]
    db.expire_all()
    s=advance_stage(db,snapshot(2,equity=205,cash=205,available_cash=0,open_positions=0))
    assert s['phase']=='waiting_for_available_funds' and not s['achieved']
    s=advance_stage(db,snapshot(3,equity=205,cash=205,available_cash=205,open_positions=0))
    assert s['action']=='stage_complete' and s['next_target']==1000
    assert s['achieved'][0]['target']==200

def test_slippage_and_fees_below_target_do_not_complete_stage(db):
    advance_stage(db,snapshot())
    s=advance_stage(db,snapshot(2,equity=199,cash=199,available_cash=199,open_positions=0))
    assert s['phase']=='accumulating' and not s['achieved']

def test_deposit_cannot_trigger_target(db):
    s=advance_stage(db,snapshot(equity=510,cash=310,available_cash=310,cumulative_external_flows=500))
    assert s['performance_equity']==110 and s['action']=='hold'

@pytest.mark.parametrize('field',['active_orders','unresolved_intents'])
def test_flat_snapshot_cannot_complete_with_uncertain_orders(db,field):
    s=advance_stage(db,snapshot(equity=205,cash=205,available_cash=205,open_positions=0,**{field:1}))
    assert not s['achieved']

def test_protective_order_does_not_deadlock_liquidation(db):
    assert advance_stage(db,snapshot(active_orders=1))['action']=='request_liquidation'

def test_snapshot_idempotency_and_policy_identity(db):
    shot=snapshot(equity=205,cash=205,available_cash=205,open_positions=0)
    one=advance_stage(db,shot); two=advance_stage(db,shot)
    assert one==two and len(two['achieved'])==1
    with pytest.raises(ValueError,match='different contents'): advance_stage(db,snapshot())
    with pytest.raises(ValueError,match='migration'): advance_stage(db,snapshot(2),MilestonePolicy(first_target=500))

def test_modes_are_isolated(db):
    advance_stage(db,snapshot())
    assert read_stage(db,'live','account')['last_observation_id'] is None

def test_first_target_range_and_full_ladder():
    p=MilestonePolicy(first_target=500)
    assert p.targets==[500,1000,3000,5000,10000,50000,100000,300000,500000,1000000]
    with pytest.raises(ValueError): MilestonePolicy(first_target=600)

def test_later_withdrawal_does_not_erase_achieved_stage(db):
    advance_stage(db,snapshot(equity=205,cash=205,available_cash=205,open_positions=0))
    s=advance_stage(db,snapshot(2,equity=105,cash=105,available_cash=105,open_positions=0,cumulative_external_flows=0))
    assert s['next_target']==1000 and len(s['achieved'])==1

def test_triggered_liquidation_does_not_wait_for_price_recovery(db):
    advance_stage(db,snapshot(active_orders=1))
    falling=snapshot(2,equity=199,active_orders=1)
    assert advance_stage(db,falling)['action']=='request_liquidation'

def test_final_milestone_does_not_reenable_entries(db):
    policy=MilestonePolicy()
    for i,target in enumerate(policy.targets,1):
        s=advance_stage(db,snapshot(i,equity=target,cash=target,available_cash=target,open_positions=0))
        assert s['action']=='stage_complete'
    s=advance_stage(db,snapshot(11,equity=1000000,cash=1000000,available_cash=1000000,open_positions=0))
    assert s['phase']=='complete' and s['next_target'] is None
