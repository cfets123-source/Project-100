from datetime import date,timedelta
from copy import deepcopy
import pytest
from app.research.cross_market_screen import evaluate,select_symbol


def fixture():
    days=[];d=date(2023,1,2)
    while d<date(2026,1,1):
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    raw={'SPY':{d:dict(open=10+i*.01,close=10+i*.01,low=10+i*.01,high=10+i*.01) for i,d in enumerate(days)}}
    return days,raw


def run(days,raw,signal=None,cost=.0005):
    return evaluate(raw,signal or raw,dates=days,start='2024-01-01',end='2026-01-01',candidate='broad_equity_trend',one_way_cost=cost)


def test_signal_excludes_future_prices_and_entry_waits_for_settlement():
    days,raw=fixture();result=run(days,raw)
    trade=result.trades[0]
    month=[d for d in days if d[:7]==trade['entry_day'][:7]]
    assert trade['entry_day']==month[2] # T+2 in February 2024
    idx=days.index(trade['entry_day']);modified=deepcopy(raw)
    for d in days[idx+1:]:
        for k in modified['SPY'][d]:modified['SPY'][d][k]*=2
    rerun=run(days,modified)
    assert result.equity[:idx-days.index('2024-01-01')+1]==rerun.equity[:idx-days.index('2024-01-01')+1]


def test_constant_prices_are_cash_and_costs_reduce_returns():
    days,raw=fixture()
    assert run(days,raw,cost=.002).equity[-1]['liquidation']<run(days,raw,cost=.0005).equity[-1]['liquidation']
    for row in raw['SPY'].values():
        for k in row:row[k]=10
    result=run(days,raw)
    assert result.cash_days==len(result.equity)
    assert not result.trades
    assert result.equity[-1]['liquidation']==100


def test_split_does_not_halve_held_value():
    days,raw=fixture();signal=deepcopy(raw)
    baseline=run(days,raw);day=baseline.trades[0]['entry_day'];idx=days.index(day)+2;splitday=days[idx]
    for d in days[idx:]:
        for k in raw['SPY'][d]:raw['SPY'][d][k]/=2
    split=evaluate(raw,signal,dates=days,start='2024-01-01',end='2026-01-01',candidate='broad_equity_trend',one_way_cost=.0005,splits={('SPY',splitday):2})
    assert split.equity[-1]['liquidation']==pytest.approx(baseline.equity[-1]['liquidation'],abs=1e-6)


def test_missing_data_is_rejected():
    days,raw=fixture();del raw['SPY'][days[500]]
    with pytest.raises(ValueError,match='missing'):run(days,raw)
