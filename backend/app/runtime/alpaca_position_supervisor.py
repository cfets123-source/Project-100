"""Existing-exposure supervision independent of strategy/entry eligibility.

Invoked under the entry worker's account lock, not as a competing writer.
The management flag is separate and defaults off. Read-only visibility works
without either execution flag. Nothing in this module chooses a new position.
"""
from app.brokers.alpaca_connection import load_read_only_adapter, load_live_execution_adapter
from app.brokers.reduce_only import ReduceOnlyAdapter
from app.services.alpaca_paper_protection import ensure_protective_stops
from app.runtime.alpaca_live_position_manager import manage_session_close, reconcile_broker_bracket_exits
from app.services.alpaca_risk_reconciliation import collect_risk_observation
from app.services.milestone_lifecycle import MilestonePolicy, StageSnapshot, advance_stage
from app.models.models import OrderIntent, DefensiveOrderIntent
from app.runtime.milestone_execution import liquidate_for_milestone
from app.brokers.reduce_only import TERMINAL, reconcile_defensive_intents
from app.services.reconciliation import reconcile_all_pending
import time
import uuid


def supervise_positions(db, cfg):
    reader, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
    if paper or reader.paper:
        raise RuntimeError('live position supervisor received paper credentials')
    accounts = reader.get_accounts()
    if len(accounts) != 1 or not accounts[0].get('account_id'):
        raise RuntimeError('position supervisor requires one identified account')
    positions = reader.get_positions()
    result = {'observed': True, 'positions': len(positions), 'management_enabled': False,
              'risk_ready': False}
    account_id = str(accounts[0]['account_id'])
    try:
        reconcile_all_pending(db, reader, account_id=account_id)
        reconcile_defensive_intents(db, reader, account_id)
        risk = collect_risk_observation(db, reader, getattr(cfg, 'STATE_SCOPE', 'current'))
        orders = reader.get_orders()
        balances = reader.get_balances()
        unresolved = db.query(OrderIntent).filter(
            OrderIntent.account_id == account_id,
            OrderIntent.status.in_(['pending','submitted','accepted','partial','unknown'])).count()
        unresolved += db.query(DefensiveOrderIntent).filter(
            DefensiveOrderIntent.account_id == account_id,
            DefensiveOrderIntent.status.in_(['unknown'])).count()
        # The broker's available cash buying power must be separately reported;
        # equity or margin buying power alone is not settlement evidence.
        available = reader._request('GET', '/v2/account').get('non_marginable_buying_power')
        if available is None:
            raise RuntimeError('cash buying-power evidence unavailable')
        stage = advance_stage(db, StageSnapshot(
            observation_id=uuid.uuid4().hex, observed_at=time.time(), account_id=account_id,
            mode='live', equity=float(balances['equity']), cash=float(balances['cash']),
            available_cash=min(float(balances['cash']), float(available)),
            cumulative_external_flows=risk['net_external_flows'], open_positions=len(positions),
            active_orders=sum(o.get('status') not in TERMINAL for o in orders),
            unresolved_intents=unresolved, reconciled=True),
            MilestonePolicy(first_target=cfg.FIRST_MILESTONE, starting_capital=cfg.STARTING_CAPITAL))
        result.update(risk_ready=True, milestone=stage)
    except Exception as exc:
        # Entry remains blocked, but a risk-data outage must not skip protection.
        result['risk_error'] = type(exc).__name__ + ': ' + str(exc)[:200]
    if not positions:
        return result
    if not getattr(cfg, 'LIVE_POSITION_MANAGEMENT_ENABLED', False):
        return {**result, 'reason': 'position_management_disabled'}
    writer = load_live_execution_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, enabled=True)
    adapter = ReduceOnlyAdapter(db, writer, str(accounts[0]['account_id']))
    if result.get('milestone', {}).get('action') == 'request_liquidation':
        result['management_enabled'] = True
        result['liquidation'] = liquidate_for_milestone(adapter)
        return result
    protection = ensure_protective_stops(db, adapter, cfg, mode='live')
    result.update(management_enabled=True, protection=protection)
    if protection.get('protected'):
        result['session_close'] = manage_session_close(db, adapter, cfg, mode='live')
    result['reconciliation'] = reconcile_broker_bracket_exits(db, adapter, mode='live')
    return result
