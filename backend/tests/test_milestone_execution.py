from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.session import Base
from app.brokers.base import OrderResult
from app.brokers.reduce_only import ReduceOnlyAdapter, reconcile_defensive_intents
from app.runtime.milestone_execution import liquidate_for_milestone
from app.services.milestone_lifecycle import StageSnapshot, advance_stage


def shot(n, flat=False, available=10):
    return StageSnapshot(observation_id=str(n),observed_at=1000+n,account_id='acct',mode='paper',
                         equity=205,cash=205 if flat else 10,available_cash=available,
                         cumulative_external_flows=100,open_positions=0 if flat else 1,
                         active_orders=0,unresolved_intents=0,reconciled=True)


def test_realized_stage_waits_for_broker_fill_then_available_cash():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    b=MagicMock(paper=True)
    b.get_accounts.return_value=[{'account_id':'acct'}]
    b.get_positions.return_value=[{'symbol':'XYZ','qty':'1'}]
    stop={'id':'stop','symbol':'XYZ','side':'sell','type':'stop','status':'accepted'}
    orders=[stop]
    b.get_orders.side_effect=lambda:list(orders)
    b.get_order_status.side_effect=lambda order_id:dict(next(o for o in orders if o['id']==order_id))
    def cancel(order_id):
        stop['status']='canceled';return True
    b.cancel_order.side_effect=cancel
    def submit(order):
        orders.append({'id':'exit','symbol':order.symbol,'side':'sell','type':'market',
                       'status':'accepted','client_order_id':order.client_order_id})
        return OrderResult('exit','accepted')
    b.place_order.side_effect=submit
    with Session(engine) as db:
        assert advance_stage(db,shot(1))['action']=='request_liquidation'
        result=liquidate_for_milestone(ReduceOnlyAdapter(db,b,'acct'))
        assert result['submitted'][0]['status']=='accepted'
        assert liquidate_for_milestone(ReduceOnlyAdapter(db,b,'acct'))['reason']=='exit_pending'
        assert b.place_order.call_count==1
        orders[1]['status']='filled'; b.get_positions.return_value=[]
        assert reconcile_defensive_intents(db,b,'acct')==[]
        assert advance_stage(db,shot(2,flat=True,available=10))['phase']=='waiting_for_available_funds'
        done=advance_stage(db,shot(3,flat=True,available=205))
        assert done['next_target']==1000 and done['action']=='stage_complete'


def test_uncertain_cancel_does_not_submit_a_sell():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    b=MagicMock(paper=True);b.get_accounts.return_value=[{'account_id':'acct'}]
    b.get_orders.return_value=[{'id':'stop','side':'sell','type':'stop','status':'accepted'}]
    b.get_order_status.return_value={'id':'stop','side':'sell','status':'pending_cancel'}
    with Session(engine) as db:
        assert liquidate_for_milestone(ReduceOnlyAdapter(db,b,'acct'))['reason']=='stop_cancel_unconfirmed'
    b.place_order.assert_not_called()
