import json,hashlib
from pathlib import Path
from datetime import date,timedelta
from dataclasses import asdict
from app.research.cross_market_screen import CANDIDATES,evaluate
ROOT=Path(__file__).resolve().parent
p=json.loads((ROOT/'source.json').read_text())
calendar=[r['date'] for r in p['calendar']]
assert calendar==sorted(set(calendar))
raw={s:{r['timestamp'][:10]:r for r in rows} for s,rows in p['securities']['raw'].items()}
signal={s:{r['timestamp'][:10]:r for r in rows} for s,rows in p['securities']['split'].items()}
coverage={};splits={}
for s in raw:
    assert set(raw[s])==set(signal[s])==set(calendar),f'equity missing dates:{s}'
    prior=None
    for d in calendar:
        ratio=raw[s][d]['close']/signal[s][d]['close']
        if prior is not None and abs(prior/ratio-1)>.003:splits[(s,d)]=prior/ratio
        prior=ratio
    coverage[s]={'first':calendar[0],'last':calendar[-1],'rows':len(raw[s])}
crypto={s:{r['timestamp'][:10]:r for r in rows} for s,rows in p['crypto'].items()}
c_dates=[];d=date(2017,1,1)
while d<date(2026,9,23):c_dates.append(d.isoformat());d+=timedelta(days=1)
for s in crypto:
    missing=sorted(set(c_dates)-set(crypto[s]));assert not missing,f'crypto missing dates:{s}:{missing[:10]}'
    coverage[s]={'first':c_dates[0],'last':c_dates[-1],'rows':len(crypto[s])}
for data in (raw,signal,crypto):
    for s,rows in data.items():
        for d,r in rows.items():
            assert 0<r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'],f'invalid OHLC:{s}:{d}'
windows=[('2018-2021','2018-01-01','2022-01-01'),('2022-2024','2022-01-01','2025-01-01'),('2025-2026','2025-01-01','2026-09-23')]
results=[]
for candidate in CANDIDATES:
    is_crypto=candidate=='crypto_rotation'
    for benchmark in ([False,True] if candidate in ('broad_equity_trend','crypto_rotation') else [False]):
        for cost_kind,cost in [('base',.0035 if is_crypto else .0005),('stress',.0075 if is_crypto else .0015)]:
            for label,start,end in windows:
                r=evaluate(crypto if is_crypto else raw,crypto if is_crypto else signal,dates=c_dates if is_crypto else calendar,start=start,end=end,candidate=candidate,one_way_cost=cost,splits=splits,benchmark=benchmark)
                peak=100.;dd=0
                for e in r.equity:peak=max(peak,e['liquidation']);dd=min(dd,e['liquidation']/peak-1)
                results.append({'candidate':candidate,'benchmark':benchmark,'window':label,'cost_kind':cost_kind,'one_way_cost':cost,'ending_liquidation':r.equity[-1]['liquidation'],'return':r.equity[-1]['liquidation']/100-1,'max_drawdown':dd,'round_trips':len(r.trades),'cash_fraction':r.cash_days/len(r.equity),'milestones':{str(m):next((e['day'] for e in r.equity if e['liquidation']>=m),None) for m in (200,500)},**asdict(r)})
screens={}
for c in CANDIDATES:
    base=[r for r in results if r['candidate']==c and not r['benchmark'] and r['cost_kind']=='base']
    reasons=[]
    for r in base:
        if r['return']<=0:reasons.append(r['window']+':nonpositive_return')
        if r['max_drawdown']<-.35:reasons.append(r['window']+':drawdown_exceeds_35_percent')
    if sum(r['round_trips'] for r in base)<12:reasons.append('too_few_completed_round_trips')
    stress=next(r for r in results if r['candidate']==c and not r['benchmark'] and r['cost_kind']=='stress' and r['window']=='2025-2026')
    if stress['return']<=0:reasons.append('recent_stress_nonpositive_return')
    screens[c]={'passed':not reasons,'reasons':reasons}
out={'coverage':coverage,'split_events':[{'symbol':s,'day':d,'factor':f} for (s,d),f in splits.items()],'screens':screens,'results':results,'live_approval':False,'source_sha256':hashlib.sha256((ROOT/'source.json').read_bytes()).hexdigest(),'plan_sha256':hashlib.sha256((ROOT/'PLAN.md').read_bytes()).hexdigest()}
(ROOT/'results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'screens':screens,'results':[{k:v for k,v in r.items() if k not in ('equity','trades')} for r in results]},indent=2))
