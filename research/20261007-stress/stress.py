import json, random, datetime as dt, statistics as st
import rot_curve as R, cbt_curve as C
def curve_alloc():
    R.run(dt.date(2011,1,3),dt.date(2026,9,25),mode='rot',margin=.2,weekly=True); return list(R.CURVE)
def curve_crypto():
    C.signals_run(dt.date(2018,1,1),dt.date(2026,9,25)); return list(C.CURVE)
def rets(cv): return [(cv[i][0], cv[i][1]/cv[i-1][1]-1) for i in range(1,len(cv)) if cv[i-1][1]>0]
def mc(rs, days, n=4000, block=20, seed=7, floor=50.0):
    rnd=random.Random(seed); r=[x for _,x in rs]; ends=[]; hit=0; mins=[]
    for _ in range(n):
        eq=100.0; lo=100.0; k=0
        while k<days:
            i=rnd.randrange(0,len(r)-block)
            for x in r[i:i+block]:
                eq*=1+x; lo=min(lo,eq); k+=1
                if k>=days: break
        ends.append(eq); mins.append(lo); hit+= lo<=floor
    ends.sort(); q=lambda p: ends[int(p*(n-1))]
    return {"paths":n,"days":days,"block":block,"p_floor":round(hit/n,4),"p5":round(q(.05),2),"median":round(q(.5),2),"p95":round(q(.95),2)}
def window(cv,a,b):
    pts=[(d,e) for d,e in cv if a<=d<=b]
    if len(pts)<2: return None
    e0=pts[0][1]; lo=min(e/e0*100 for _,e in pts)
    return {"start":str(a),"end":str(b),"end_value":round(pts[-1][1]/e0*100,2),"lowest":round(lo,2)}
GATE={"max_p_floor":0.10,"crash_min_above":50.0,"rule":"P(touch $50 within 12 months) <= 10% in a 4,000-path 20-day block bootstrap of the backtest's daily returns, AND starting from $100 the account never falls to $50 inside any listed historical crash window."}
out={"generated":str(dt.date.today()),"gate":GATE,"strategies":{}}
for name,fn,days,wins in [("allocator-core-satellite-v1",curve_alloc,252,[(dt.date(2020,2,19),dt.date(2020,3,23),"COVID crash"),(dt.date(2022,1,3),dt.date(2022,12,30),"2022 bear market"),(dt.date(2018,9,20),dt.date(2018,12,24),"Q4 2018 selloff")]),
                          ("binance-crypto-signals-v1",curve_crypto,365,[(dt.date(2018,1,6),dt.date(2018,12,15),"2018 crypto winter"),(dt.date(2020,3,1),dt.date(2020,3,31),"March 2020"),(dt.date(2021,11,8),dt.date(2022,11,21),"2022 crypto bear")])]:
    cv=fn(); rs=rets(cv); m=mc(rs,days)
    crashes=[{**window(cv,a,b),"name":nm} for a,b,nm in wins if window(cv,a,b)]
    passed = m["p_floor"]<=GATE["max_p_floor"] and all(c["lowest"]>GATE["crash_min_above"] for c in crashes)
    out["strategies"][name]={"sample":f"{cv[0][0]}..{cv[-1][0]}","monte_carlo_12m":m,"crashes":crashes,"passed":passed}
    print(name, json.dumps(out["strategies"][name], indent=1))
json.dump(out,open('/tmp/claude-0/stress_results.json','w'),indent=1)
# daily-return bands for the nightly review (what a "normal" day looks like in the backtest)
for name,fn in [("allocator-core-satellite-v1",curve_alloc),("binance-crypto-signals-v1",curve_crypto)]:
    r=sorted(x for _,x in rets(fn())); q=lambda p:r[int(p*(len(r)-1))]
    out["strategies"][name]["daily_return_bands"]={"p01":round(q(.01),4),"p05":round(q(.05),4),"p95":round(q(.95),4),"p99":round(q(.99),4)}
    out["strategies"][name]["backtest_max_drawdown"]=None
json.dump(out,open('/tmp/claude-0/stress_results.json','w'),indent=1)
print({k:v["daily_return_bands"] for k,v in out["strategies"].items()})
