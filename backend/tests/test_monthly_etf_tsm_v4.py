from datetime import date,timedelta
import pytest
from app.research.monthly_etf_time_series_momentum_v4 import evaluate,settlement_sessions,UNIVERSE

@pytest.mark.parametrize('day,expected', [('2017-09-01',3),('2017-09-05',2),('2024-05-24',2),('2024-05-28',1)])
def test_settlement_regime(day,expected):
    assert settlement_sessions(day)==expected

def fixture_data(year):
    days=[];day=date(year-2,1,1)
    while day<date(year+1,1,1):
        if day.weekday()<5:days.append(day.isoformat())
        day+=timedelta(days=1)
    data={}
    for symbol in UNIVERSE:
        data[symbol]=[]
        for i,day in enumerate(days):
            price=20+i*.01 if symbol=='XLF' else 20
            data[symbol].append(dict(timestamp=day,open=price,high=price,low=price,close=price))
    return days,data

@pytest.mark.parametrize('year,delay',[(2017,3),(2023,2),(2025,1)])
def test_monthly_entry_waits_for_settlement(year,delay):
    days,data=fixture_data(year)
    result=evaluate(data,data,raw_adjustment='raw',signal_adjustment='split',split_events={},
                    start=f'{year}-01-01',end=f'{year+1}-01-01')
    assert result.trades
    trade=result.trades[0]
    month_days=[d for d in days if d[:7]==trade.entry_day[:7]]
    assert trade.entry_day==month_days[delay]
    assert trade.shares*trade.entry<=95


def test_gap_exit_and_future_data_cannot_change_prior_entries():
    days,data=fixture_data(2025)
    kwargs=dict(raw_adjustment='raw',signal_adjustment='split',split_events={},start='2025-01-01',end='2026-01-01')
    baseline=evaluate(data,data,**kwargs)
    trade=baseline.trades[0]
    idx=days.index(trade.entry_day)+1
    gap=trade.entry*.5
    data[trade.symbol][idx].update(open=gap,high=gap,low=gap,close=gap)
    result=evaluate(data,data,**kwargs)
    assert result.trades[0].entry_day==trade.entry_day
    assert result.trades[0].exit==gap
    assert result.trades[0].reason=='stop'
    assert result.breaker_events>=1
