import time
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.session import Base
from app.models.models import SystemStateRecord, DefensiveOrderIntent, RiskReservation, OrderIntent
from app.services.state_machine import StateManager
from app.services.account_risk import record_observation, measured_risk_context, RiskEvidenceUnavailable
from app.brokers.reduce_only import ReduceOnlyAdapter
from app.brokers.base import OrderRequest, OrderResult, Quote
from app.runtime.alpaca_live_position_manager import release_flat_account_reservations
from app.runtime import alpaca_live_worker
from app.risk.engine import RiskEngine, TradeProposal
from app.core.config import Settings

@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session: yield session

def test_paper_halt_does_not_touch_live_state(db):
    db.add_all([SystemStateRecord(id='alpaca:paper', state='paper'), SystemStateRecord(id='alpaca:live', state='live')]); db.commit()
    StateManager(db, SimpleNamespace(STATE_SCOPE='alpaca:paper')).activate_kill_switch('paper failure')
    assert StateManager(db, SimpleNamespace(STATE_SCOPE='alpaca:live')).get_state() == 'live'

@pytest.mark.parametrize('legacy,expected', [('halted', 'halted'), ('live', 'off'), ('paper', 'off')])
def test_scope_migration_preserves_halt_but_never_copies_permissions(db, legacy, expected):
    db.add(SystemStateRecord(id='current', state=legacy, reason='existing')); db.commit()
    assert StateManager(db, SimpleNamespace(STATE_SCOPE='alpaca:live')).get_state() == expected
    assert db.get(SystemStateRecord, 'current').state == legacy

def observation(db, **updates):
    args = dict(scope='alpaca:live', account_id='acct', observed_at=time.time(), equity=90., adjusted_day_open=100., adjusted_week_peak=105., adjusted_all_time_peak=110., net_external_flows=0., reconciled=True)
    args.update(updates); return record_observation(db, **args)

def context(db, **updates):
    args = dict(scope='alpaca:live', account_id='acct', equity=90., avg_dollar_volume=5_000_000)
    args.update(updates); return measured_risk_context(db, **args)

def test_measured_losses_reach_risk_engine_and_block_order(db):
    observation(db); risk = context(db)
    assert risk['daily_pnl_pct'] == pytest.approx(-.10)
    assert risk['weekly_drawdown_pct'] == pytest.approx(1-90/105)
    assert risk['total_drawdown_pct'] == pytest.approx(1-90/110)
    quote = Quote('test', 'XYZ', time.time(), 0, 9.99, 10.01, 10, 'open')
    decision = RiskEngine(Settings()).evaluate(TradeProposal(symbol='XYZ', direction='long', entry_price=10, stop_price=9, quote=quote, strategy='test', account_equity=90, **risk))
    assert not decision.approved
    assert 'weekly_drawdown_limit_reached' in decision.reasons
    assert 'total_drawdown_limit_reached' in decision.reasons

def test_missing_stale_wrong_account_and_changed_equity_fail_closed(db):
    with pytest.raises(RiskEvidenceUnavailable): context(db)
    observation(db)
    for changes in [dict(now=time.time()+120), dict(account_id='other'), dict(equity=95)]:
        with pytest.raises(RiskEvidenceUnavailable): context(db, **changes)

def test_cashflow_adjusted_baselines_and_restart(db):
    observation(db, equity=150, adjusted_day_open=150, adjusted_week_peak=150, adjusted_all_time_peak=160, net_external_flows=50)
    db.expire_all(); result = context(db, equity=150)
    assert result['daily_pnl_pct'] == 0
    assert result['total_drawdown_pct'] == pytest.approx(1-150/160)

def test_supervision_runs_before_entry_validation_and_survives_rejection(monkeypatch):
    events=[]
    monkeypatch.setattr(alpaca_live_worker, 'supervise_positions', lambda *a: events.append('supervised') or {'observed': True})
    def refuse(*a):
        events.append('entry_gate'); raise RuntimeError('strategy no longer approved')
    monkeypatch.setattr(alpaca_live_worker, 'start_live_worker', refuse)
    result = alpaca_live_worker.run_cycle(object(), object())
    assert events == ['supervised', 'entry_gate']
    assert result['entries'] == [] and result['supervision']['observed']

def broker():
    b = MagicMock(paper=False)
    b.get_accounts.return_value = [{'account_id': 'acct'}]
    b.get_positions.return_value = [{'symbol': 'XYZ', 'qty': '1'}]
    b.get_orders.return_value = []
    b.place_order.return_value = OrderResult('sell-1', 'accepted')
    return b

@pytest.mark.parametrize('side,qty', [('buy',1), ('sell',2), ('sell',0), ('sell',float('nan'))])
def test_supervisor_cannot_increase_exposure(db, side, qty):
    b = broker()
    with pytest.raises(RuntimeError): ReduceOnlyAdapter(db,b,'acct').place_order(OrderRequest('XYZ',side,qty))
    b.place_order.assert_not_called()

def test_uncertain_sell_survives_restart_without_duplicate(db):
    b=broker(); b.place_order.side_effect=TimeoutError()
    with pytest.raises(TimeoutError): ReduceOnlyAdapter(db,b,'acct').place_order(OrderRequest('XYZ','sell',1))
    assert db.query(DefensiveOrderIntent).one().status == 'unknown'
    b.get_order_by_client_id.side_effect=RuntimeError('not yet visible')
    with pytest.raises(RuntimeError, match='unresolved'):
        ReduceOnlyAdapter(db,b,'acct').place_order(OrderRequest('XYZ','sell',1))
    assert b.place_order.call_count == 1

def test_pending_sell_blocks_duplicate_even_if_position_is_unchanged(db):
    b=broker(); b.get_orders.return_value=[{'symbol':'XYZ','side':'sell','status':'pending_cancel'}]
    with pytest.raises(RuntimeError,match='duplicate'):
        ReduceOnlyAdapter(db,b,'acct').place_order(OrderRequest('XYZ','sell',1))
    b.place_order.assert_not_called()

def test_pending_intent_reservation_not_released_by_flat_snapshot(db):
    db.add(RiskReservation(id='keep', account_id='acct', decision_id='decision', risk_dollars=1, notional=10, status='active'))
    db.add(OrderIntent(intent_key='intent',account_id='acct',decision_id='decision',symbol='XYZ',side='buy',quantity=1,status='unknown')); db.commit()
    b=broker();b.get_positions.return_value=[]
    assert release_flat_account_reservations(db,b,'acct') == []
    assert db.get(RiskReservation,'keep').status == 'active'

def test_partial_defensive_fills_do_not_close_trade_until_flat_and_complete(db):
    from app.models.models import TradeDecisionRecord
    from app.brokers.reduce_only import reconcile_defensive_intents
    trade=TradeDecisionRecord(symbol='XYZ',strategy='test',direction='long',order_id='entry',
                              fill_price=100,position_size=1,status='open')
    db.add(trade)
    db.add_all([
        DefensiveOrderIntent(client_order_id='part',account_id='acct',symbol='XYZ',quantity=1,
                             broker_order_id='exit-1',entry_order_id='entry',status='unknown'),
        DefensiveOrderIntent(client_order_id='rest',account_id='acct',symbol='XYZ',quantity=.6,
                             broker_order_id='exit-2',entry_order_id='entry',status='unknown')])
    db.commit()
    b=broker()
    orders={'exit-1':{'id':'exit-1','client_order_id':'part','symbol':'XYZ','side':'sell',
                      'status':'canceled','filled_qty':'.4','filled_avg_price':'110'},
            'exit-2':{'id':'exit-2','client_order_id':'rest','symbol':'XYZ','side':'sell',
                      'status':'partially_filled','filled_qty':'.3','filled_avg_price':'120'},
            'entry':{'id':'entry','symbol':'XYZ','side':'buy','status':'filled','filled_qty':'1'}}
    b.get_order_status.side_effect=lambda order_id:orders[order_id]
    reconcile_defensive_intents(db,b,'acct')
    assert trade.status=='open'
    orders['exit-2'].update(status='filled',filled_qty='.6')
    b.get_positions.return_value=[]
    reconcile_defensive_intents(db,b,'acct')
    assert trade.status=='closed' and trade.pnl==pytest.approx(16)
    assert trade.exit_price==pytest.approx(116)
