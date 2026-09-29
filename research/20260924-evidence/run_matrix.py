"""Frozen historical research matrix; no DB or broker access."""
import hashlib,json,math
from pathlib import Path
from dataclasses import asdict
from app.research import monthly_etf_time_series_momentum_v3 as v3
from app.research import monthly_etf_time_series_momentum_v4 as v4
ROOT=Path(__file__).resolve().parent
source=ROOT/'sip-bars.json'
payload=json.loads(source.read_text())
# API end is inclusive; preserve source and apply the predeclared exclusive end.
raw,signal=[{s:[r for r in rows if r['timestamp'][:10] < payload['end']] for s,rows in payload['data'][k].items()} for k in ('raw','split')]
expected={r['date'] for r in payload['calendar']}
coverage={}
splits={}
warmup_only_splits=[]
for symbol in v4.UNIVERSE:
    by_kind={kind:{r['timestamp'][:10]:r for r in data[symbol]} for kind,data in [('raw',raw),('split',signal)]}
    for kind,data in [('raw',raw),('split',signal)]:
        dates=set(by_kind[kind])
        assert len(dates)==len(data[symbol]),f'duplicate bars:{symbol}:{kind}'
        missing=sorted(expected-dates)
        assert not missing,f'missing sessions:{symbol}:{kind}:{missing[:10]}'
        assert dates==expected,f'extra sessions:{symbol}:{kind}'
        for row in data[symbol]:
            assert all(math.isfinite(float(row[k])) and float(row[k])>0 for k in ('open','high','low','close'))
            assert row['low']<=min(row['open'],row['close'])<=max(row['open'],row['close'])<=row['high']
    previous=None
    for day in sorted(expected):
        ratio=by_kind['raw'][day]['close']/by_kind['split'][day]['close']
        if previous is not None:
            factor=previous/ratio
            if abs(factor-1)>.002:
                if day < '2017-01-01':
                    # No modeled position exists in indicator warmup; official
                    # split-adjusted signals already incorporate these events.
                    warmup_only_splits.append({'symbol':symbol,'day':day,'factor':factor})
                else:
                    assert abs(factor-round(factor))<.002 and round(factor)>=2,f'ambiguous split:{symbol}:{day}:{factor}'
                    splits[(symbol,day)]=round(factor)
        previous=ratio
    coverage[symbol]={'bars':len(expected),'first':min(expected),'last':max(expected)}
windows=[('2017-2021','2017-01-01','2022-01-01'),('2022-2024','2022-01-01','2025-01-01'),('2025-2026','2025-01-01','2026-09-23')]
results=[]
for version,model in [('v3',v3),('v4',v4)]:
    for name,start,end in windows:
        assert sum(d<start for d in expected)>=252,f'insufficient warmup:{name}'
        for cost in (.001,.002,.005):
            result=model.evaluate(raw,signal,raw_adjustment='raw',signal_adjustment='split',split_events=splits,start=start,end=end,cost=cost)
            peak=100.;dd=0
            for _,eq in result.equity:
                peak=max(peak,eq);dd=min(dd,eq/peak-1)
            results.append({'version':version,'window':name,'cost':cost,'trades':len(result.trades),
                'ending_equity':result.equity[-1][1],'return':result.equity[-1][1]/100-1,
                'max_drawdown':dd,'milestones':{str(m):next((d for d,e in result.equity if e>=m),None) for m in (200,500)},
                'open_at_end':result.open_at_end,'unavailable_entries':result.unavailable_entries,
                'breaker_events':result.breaker_events,'equity':result.equity,'trade_ledger':[asdict(t) for t in result.trades]})
primary=[r for r in results if r['version']=='v4' and r['cost']==.001]
stress=next(r for r in results if r['version']=='v4' and r['window']=='2025-2026' and r['cost']==.002)
reasons=[]
for r in primary:
    if r['return']<=0:reasons.append(r['window']+':nonpositive_return')
    if r['max_drawdown']<=-.25:reasons.append(r['window']+':drawdown_at_least_25_percent')
if primary[-1]['trades']<10:reasons.append('recent:insufficient_completed_trades')
if stress['return']<=0:reasons.append('recent:nonpositive_stressed_return')
output={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'plan_sha256':hashlib.sha256((ROOT/'PLAN.md').read_bytes()).hexdigest(),'coverage':coverage,'warmup_only_splits':warmup_only_splits,'split_events':[{'symbol':s,'day':d,'factor':f} for (s,d),f in splits.items()],'results':results,'historical_screen_passed':not reasons,'reasons':reasons,'live_approval':False}
(ROOT/'results.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({**{k:v for k,v in output.items() if k not in ('coverage','results')},'results':[{k:v for k,v in r.items() if k not in ('equity','trade_ledger')} for r in results]},indent=2))
