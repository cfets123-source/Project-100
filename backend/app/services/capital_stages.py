"""Persisted PAPER milestone policy. Never changes execution permissions or risk.

Thresholds are engineering policy, not a claim of statistical proof or growth.
There is deliberately no deposit/top-up operation in this simulated account.
"""
from copy import deepcopy
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.audit.logger import log_and_commit
from app.analytics.performance import closed_trades, summarize
from app.models.models import CapitalStageState, OrderIntent


class StagePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    opening_milestone: Literal[500, 1000] = 1000
    intermediate_milestone: Literal[300000, 500000] = 500000
    minimum_trades: int = Field(default=50, ge=2)
    minimum_losses: int = Field(default=5, ge=1)
    minimum_profit_factor: float = Field(default=1.2, gt=1)
    minimum_trade_sharpe: float = Field(default=.2, ge=0)
    maximum_drawdown: float = Field(default=.10, gt=0, lt=1)

    @property
    def milestones(self):
        return ([500] if self.opening_milestone == 500 else []) + [1000, 10000, 100000] + ([300000] if self.intermediate_milestone == 300000 else []) + [500000, 1000000]


def evaluate_paper_stage(db, equity, max_drawdown, healthy, policy=None):
    policy = policy or StagePolicy()
    if not math.isfinite(equity) or equity < 0 or not math.isfinite(max_drawdown) or max_drawdown < 0:
        raise ValueError('invalid milestone inputs')
    row = db.get(CapitalStageState, 'paper:paper-1')
    if row is None:
        row = CapitalStageState(id='paper:paper-1', payload={'index': 0, 'used_trade_ids': [],
            'policy': policy.model_dump(), 'last_action': 'hold', 'reasons': ['insufficient_history']})
        db.add(row)
        db.flush()
    state = deepcopy(row.payload)
    # Older persisted policies predate the optional $500 waypoint.  Their
    # default remains $1,000; an intentional switch to $500 still requires a
    # stage migration rather than silently reinterpreting an achieved index.
    if StagePolicy.model_validate(state['policy']).model_dump() != policy.model_dump():
        raise ValueError('stage policy changes require an explicit migration; no silent relaxation')
    all_trades = closed_trades(db, 'paper-1')
    used = set(state['used_trade_ids'])
    metrics = summarize([trade for trade in all_trades if trade.trade_id not in used])
    milestones = policy.milestones
    index = state['index']
    action, reasons = 'hold', []
    # Capital retracement lowers the scoreboard tier, never increases risk to recover it.
    supported = sum(equity >= threshold for threshold in milestones)
    if supported < index:
        index = supported
        state['used_trade_ids'] = [trade.trade_id for trade in all_trades]
        action, reasons = 'demote', ['equity_below_achieved_milestone']
    else:
        if index == len(milestones):
            reasons.append('all_milestones_recorded')
        elif equity < milestones[index]:
            reasons.append('capital_milestone_not_reached')
        if metrics['sample_size'] < policy.minimum_trades:
            reasons.append('insufficient_trade_sample')
        if metrics['losses'] < policy.minimum_losses:
            reasons.append('insufficient_loss_observations')
        if metrics['expectancy'] is None or metrics['expectancy'] <= 0:
            reasons.append('nonpositive_or_unknown_expectancy')
        if metrics['profit_factor'] is None or metrics['profit_factor'] < policy.minimum_profit_factor:
            reasons.append('profit_factor_below_threshold')
        if metrics['trade_sharpe_like'] is None or metrics['trade_sharpe_like'] < policy.minimum_trade_sharpe:
            reasons.append('risk_adjusted_metric_below_threshold')
        if max_drawdown > policy.maximum_drawdown:
            reasons.append('drawdown_above_threshold')
        unresolved = db.query(OrderIntent).filter(OrderIntent.account_id == 'paper-1',
            OrderIntent.status.in_(['pending','submitted','accepted','partial','unknown'])).count()
        if not healthy or unresolved:
            reasons.append('unresolved_system_or_order_issue')
        if not reasons:
            index += 1  # At most one gate per evaluation, with new evidence needed next time.
            state['used_trade_ids'] = [trade.trade_id for trade in all_trades]
            action = 'graduate'
    state.update(index=index, last_action=action, reasons=reasons,
                 next_milestone=milestones[index] if index < len(milestones) else None,
                 achieved_milestones=milestones[:index], evaluation_metrics=metrics,
                 simulated=True, risk_configuration_changed=False)
    row.payload = state
    if action != 'hold':
        log_and_commit(db, 'paper_capital_stage_changed', {'action': action, 'equity': equity, **state})
    return state
