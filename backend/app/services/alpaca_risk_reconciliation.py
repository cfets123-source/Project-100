"""Read-only Alpaca evidence collection for cash-flow-adjusted loss limits.

Uses account equity, daily portfolio history and the complete activity ledger.
Ambiguous securities transfers/journals require explicit reconciliation; they
are never silently treated as profits. Daily history cannot prove an intraday
peak before this collector began; the persistent observation preserves peaks
observed after startup.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math

from app.models.models import AccountRiskObservation
from app.services.account_risk import record_observation, RiskEvidenceUnavailable

NY = ZoneInfo('America/New_York')
CASH_TRANSFERS = {'CSD', 'CSW', 'ACATC'}
NON_TRANSFER = {'FILL','CFEE','CGD','DIV','DIVCGL','DIVCGS','DIVFEE','DIVFT','DIVNRA',
                'DIVROC','DIVTW','DIVTXEX','FEE','INT','INTNRA','INTTW','PTC','PTR',
                'OPASN','OPEXP','OPXRC','SC','SSP','NC'}


def collect_risk_observation(db, adapter, scope, *, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NY).date()
    account = adapter._request('GET', '/v2/account')
    identity = str(account.get('id') or '')
    if not identity or not account.get('created_at'):
        raise RiskEvidenceUnavailable('broker account identity/history start is missing')
    history = adapter._request('GET', '/v2/account/portfolio/history', params={
        'start': account['created_at'], 'end': now.isoformat(), 'timeframe': '1D'})
    activities, seen, token = [], set(), None
    for _ in range(100):
        page = adapter._request('GET', '/v2/account/activities', params={
            'direction': 'asc', 'page_size': 100, **({'page_token': token} if token else {})})
        if not isinstance(page, list):
            raise RiskEvidenceUnavailable('invalid broker activity response')
        for activity in page:
            if not activity.get('id') or activity['id'] in seen:
                raise RiskEvidenceUnavailable('incomplete or repeated activity pagination')
            seen.add(activity['id']); activities.append(activity)
        if len(page) < 100: break
        token = page[-1]['id']
    else:
        raise RiskEvidenceUnavailable('activity pagination limit reached; history incomplete')
    flows = []
    for a in activities:
        kind = a.get('activity_type')
        if kind in CASH_TRANSFERS:
            date = datetime.fromisoformat(str(a['date'])[:10]).date()
            amount = float(a['net_amount'])
            if not math.isfinite(amount) or date > today:
                raise RiskEvidenceUnavailable('invalid cash transfer evidence')
            flows.append((date, amount))
        elif kind not in NON_TRANSFER:
            raise RiskEvidenceUnavailable(f'activity requires explicit reconciliation: {kind}')
    total_flows = sum(amount for _,amount in flows)
    current = float(account['equity'])
    day_open = float(account['last_equity']) + sum(amount for date,amount in flows if date == today)
    timestamps, equities = history.get('timestamp', []), history.get('equity', [])
    if len(timestamps) != len(equities):
        raise RiskEvidenceUnavailable('incomplete equity history')
    points = []
    for timestamp, equity in zip(timestamps, equities):
        date = datetime.fromtimestamp(timestamp, NY).date()
        value = float(equity)
        if not math.isfinite(value):
            raise RiskEvidenceUnavailable('invalid historical equity')
        if date < today and value > 0:
            adjusted = value + sum(amount for flow_date,amount in flows if flow_date > date)
            points.append((date, adjusted))
    if not points or day_open <= 0:
        raise RiskEvidenceUnavailable('funded prior-session equity history is required')
    monday = today - timedelta(days=today.weekday())
    prior = [p for p in points if p[0] < monday]
    weekly = [value for date,value in points if date >= monday]
    if prior: weekly.append(max(prior, key=lambda p:p[0])[1])
    week_peak = max([current, day_open, *weekly])
    all_peak = max([current, day_open, *(value for _,value in points)])
    previous = db.get(AccountRiskObservation, scope)
    if previous:
        data = previous.payload
        delta = total_flows - data['net_external_flows']
        all_peak = max(all_peak, data['adjusted_all_time_peak'] + delta)
        previous_date = datetime.fromtimestamp(data['observed_at'], NY).date()
        if previous_date >= monday:
            week_peak = max(week_peak, data['adjusted_week_peak'] + delta)
    # Reject a moving funding baseline: never mix before/after transfer snapshots.
    check = adapter._request('GET', '/v2/account')
    if (str(check.get('id')) != identity or float(check['cash']) != float(account['cash'])
            or abs(float(check['equity'])-current) > max(.01,current*.001)):
        raise RiskEvidenceUnavailable('account changed during reconciliation')
    return record_observation(db, scope=scope, account_id=identity, observed_at=now.timestamp(),
                              equity=current, adjusted_day_open=day_open,
                              adjusted_week_peak=week_peak, adjusted_all_time_peak=all_peak,
                              net_external_flows=total_flows, reconciled=True)
