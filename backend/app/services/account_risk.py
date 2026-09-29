"""Measured account risk. Missing evidence cannot be substituted with zero losses.

A reconciler supplies cash-flow-adjusted baselines. Observations are account
bound and expire; this module never places orders or infers transfers from P&L.
"""
import math
from datetime import datetime, timezone

from app.models.models import AccountRiskObservation


class RiskEvidenceUnavailable(RuntimeError):
    pass


def record_observation(db, *, scope, account_id, observed_at, equity,
                       adjusted_day_open, adjusted_week_peak, adjusted_all_time_peak,
                       net_external_flows, reconciled):
    values = (equity, adjusted_day_open, adjusted_week_peak, adjusted_all_time_peak,
              net_external_flows, observed_at)
    if not reconciled or not account_id or not scope:
        raise RiskEvidenceUnavailable('account risk evidence must be reconciled and identified')
    if not all(math.isfinite(float(v)) for v in values) or min(values[:4]) <= 0:
        raise RiskEvidenceUnavailable('invalid account risk evidence')
    if observed_at > datetime.now(timezone.utc).timestamp() + 5:
        raise RiskEvidenceUnavailable('future account risk evidence')
    payload = dict(account_id=account_id, observed_at=observed_at, equity=equity,
                   adjusted_day_open=adjusted_day_open, adjusted_week_peak=adjusted_week_peak,
                   adjusted_all_time_peak=adjusted_all_time_peak,
                   net_external_flows=net_external_flows, reconciled=True)
    row = db.get(AccountRiskObservation, scope)
    if row:
        if row.payload['account_id'] != account_id:
            raise RiskEvidenceUnavailable('risk scope account changed; explicit migration required')
        if row.payload['observed_at'] > observed_at:
            raise RiskEvidenceUnavailable('out-of-order account risk evidence')
        row.payload = payload
    else:
        db.add(AccountRiskObservation(scope=scope, payload=payload))
    db.commit()
    return payload


def measured_risk_context(db, *, scope, account_id, equity, avg_dollar_volume,
                          now=None, maximum_age=60):
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    row = db.get(AccountRiskObservation, scope)
    if row is None:
        raise RiskEvidenceUnavailable('reconciled account risk history is missing')
    data = row.payload
    if data['account_id'] != account_id or data.get('reconciled') is not True:
        raise RiskEvidenceUnavailable('account risk evidence identity mismatch')
    age = now - data['observed_at']
    if age < -5 or age > maximum_age:
        raise RiskEvidenceUnavailable('account risk evidence is stale')
    if not math.isfinite(equity) or equity <= 0 or not math.isfinite(avg_dollar_volume) or avg_dollar_volume <= 0:
        raise RiskEvidenceUnavailable('equity or observed liquidity is invalid')
    if abs(equity - data['equity']) > max(.01, equity * .001):
        raise RiskEvidenceUnavailable('account changed since risk reconciliation')
    return dict(avg_dollar_volume=avg_dollar_volume, sector=None, open_position_count=0,
                daily_pnl_pct=equity / data['adjusted_day_open'] - 1,
                weekly_drawdown_pct=max(0., 1 - equity / data['adjusted_week_peak']),
                total_drawdown_pct=max(0., 1 - equity / data['adjusted_all_time_peak']))
