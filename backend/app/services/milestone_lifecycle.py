"""Durable stage-by-stage target, liquidation and proceeds verification.

This module decides lifecycle actions, not trade selection, sizing or orders.
A caller must execute request_liquidation through its separately authorized
broker path, and return a new reconciled snapshot. Paper/live keys are distinct.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pydantic import BaseModel, ConfigDict, Field
from app.models.models import CapitalStageState


class MilestonePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False)
    version: str = 'staged-realized-proceeds-v1'
    starting_capital: float = Field(default=100, gt=0, lt=200)
    first_target: float = Field(default=200, ge=200, le=500)

    @property
    def targets(self):
        return [self.first_target, 1000, 3000, 5000, 10000, 50000, 100000, 300000, 500000, 1000000]


class StageSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    observation_id: str = Field(min_length=1)
    observed_at: float = Field(gt=0)
    account_id: str = Field(min_length=1)
    mode: str
    equity: float = Field(ge=0)
    cash: float = Field(ge=0)
    available_cash: float = Field(ge=0)
    # Includes the original funding. Starting capital is restored in performance
    # equity, so subsequent deposits cannot produce milestone achievements.
    cumulative_external_flows: float
    open_positions: int = Field(ge=0)
    active_orders: int = Field(ge=0)
    unresolved_intents: int = Field(ge=0)
    reconciled: bool


def stage_key(mode, account_id):
    if mode not in {'paper','live'} or not account_id:
        raise ValueError('milestone account/mode is invalid')
    return 'milestones:' + mode + ':' + account_id


def initial_state(policy):
    return dict(policy=policy.model_dump(), index=0, phase='accumulating', achieved=[],
                next_target=policy.targets[0], action='hold', reason='awaiting_reconciled_account',
                last_observed_at=0, last_observation_id=None, snapshot_hash=None)


def read_stage(db, mode, account_id, policy=None):
    policy = policy or MilestonePolicy()
    row = db.get(CapitalStageState, stage_key(mode, account_id))
    return deepcopy(row.payload) if row else initial_state(policy)


def advance_stage(db, snapshot: StageSnapshot, policy=None):
    policy = policy or MilestonePolicy()
    key = stage_key(snapshot.mode, snapshot.account_id)
    row = db.get(CapitalStageState, key)
    state = deepcopy(row.payload) if row else initial_state(policy)
    if state['policy'] != policy.model_dump():
        raise ValueError('milestone policy change requires explicit migration')
    fingerprint = sha256(json.dumps(snapshot.model_dump(),sort_keys=True).encode()).hexdigest()
    if snapshot.observation_id == state['last_observation_id']:
        if fingerprint != state['snapshot_hash']:
            raise ValueError('same observation id has different contents')
        return state
    if snapshot.observed_at <= state['last_observed_at']:
        raise ValueError('milestone snapshot is out of order')
    if not snapshot.reconciled:
        raise ValueError('milestone snapshot is not reconciled')
    if snapshot.available_cash > snapshot.cash + .005 or snapshot.cash > snapshot.equity + .005:
        raise ValueError('inconsistent long-only account snapshot')
    adjusted = policy.starting_capital + snapshot.equity - snapshot.cumulative_external_flows
    realized = policy.starting_capital + snapshot.cash - snapshot.cumulative_external_flows
    available = policy.starting_capital + snapshot.available_cash - snapshot.cumulative_external_flows
    state.update(last_observed_at=snapshot.observed_at,last_observation_id=snapshot.observation_id,
                 snapshot_hash=fingerprint, equity=snapshot.equity, performance_equity=adjusted,
                 realized_equity=realized, available_cash=snapshot.available_cash,
                 mode=snapshot.mode, account_id=snapshot.account_id, action='hold')
    index=state['index']
    if index >= len(policy.targets):
        state.update(phase='complete',reason='all_stages_completed',next_target=None)
    else:
        target=policy.targets[index]
        if snapshot.unresolved_intents or snapshot.active_orders:
            state.update(reason='orders_require_reconciliation')
            # Protective orders remain active at a reached target; the authorized
            # liquidator coordinates cancellation rather than waiting forever.
            if (state['phase'] == 'liquidating' or adjusted >= target) and snapshot.open_positions and not snapshot.unresolved_intents:
                state.update(phase='liquidating',action='request_liquidation')
        elif snapshot.open_positions:
            if state['phase']=='liquidating' or adjusted >= target:
                state.update(phase='liquidating',action='request_liquidation',reason='target_reached_sell_then_reconcile')
            else:
                state.update(phase='accumulating',reason='target_not_reached')
        elif realized < target or snapshot.cash < target:
            state.update(phase='accumulating',reason='realized_proceeds_below_target')
        elif available < target or snapshot.available_cash < target:
            state.update(phase='waiting_for_available_funds',reason='sale_proceeds_not_available')
        else:
            # Complete at most one stage per observation; no future strategy is
            # implicitly activated even if a single jump passes multiple targets.
            state['achieved'].append(dict(target=target, observed_at=snapshot.observed_at,
                                           realized_equity=realized, available_cash=snapshot.available_cash))
            state['index']=index+1
            state.update(phase='stage_complete',action='stage_complete',reason='flat_and_proceeds_reconciled',
                         next_target=policy.targets[index+1] if index+1<len(policy.targets) else None)
    if row: row.payload=state
    else: db.add(CapitalStageState(id=key,payload=state))
    db.commit()
    return state
