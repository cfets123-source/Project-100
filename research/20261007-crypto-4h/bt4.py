import json, sys, random, datetime as dt
sys.path.insert(0,'/home/claude/p100/backend')
from app.research.multi_market_rules import indicators, fires, rule_exit, RULES
C=.0005
def load(s,iv):
    rows=json.load(open(f"{s}_{iv}.json"))
    return [{"t":dt.datetime.utcfromtimestamp(r[0]/1000),"open":float(r[1]),"high":float(r[2]),"low":float(r[3]),"close":float(r[4])} for r in rows]
SY=("BTCUSD","ETHUSD","SOLUSD")
def run(iv, scale=1.0, holdmul=1, a=None, b=None, curve=None):
    data={s:load(s,iv) for s in SY}; X={s:indicators(data[s]) for s in SY}
    idx={s:{r["t"]:k for k,r in enumerate(data[s])} for s in SY}
    times=sorted(set(t for s in SY for t in idx[s]))
    if a: times=[t for t in times if a<=t<=b]
    cash=100.0;sat=[];peak=100;mdd=0;n=0;pend=[]
    for t in times:
        # entries from signals on previous bar
        eq=cash+sum(p["q"]*p["last"] for p in sat)
        for s,r in pend:
            k=idx[s].get(t)
            if k is None or any(p["s"]==s for p in sat) or len(sat)>=3: continue
            st=min(cash,eq/3)
            if st<1: break
            R=RULES[r];po=data[s][k]["open"]*(1+C)
            sat.append(dict(s=s,r=r,q=st/po,stop=po*(1-R.stop*scale),tgt=po*(1+R.target*scale),n=0,hold=R.max_hold*holdmul,last=po,x=False,k0=k));cash-=st;n+=1
        pend=[]
        for p in list(sat):
            k=idx[p["s"]].get(t)
            if k is None: continue
            b_=data[p["s"]][k];px=None
            if k>p["k0"] or True:
                if p["x"]: px=b_["open"]
                elif b_["low"]<=p["stop"]: px=min(b_["open"],p["stop"])
                elif b_["high"]>=p["tgt"]: px=max(b_["open"],p["tgt"])
            if px: cash+=p["q"]*px*(1-C);sat.remove(p);continue
            p["last"]=b_["close"];p["n"]+=1
            if p["n"]>=p["hold"] or rule_exit(p["r"],X[p["s"]],k): p["x"]=True
        for s in SY:
            k=idx[s].get(t)
            if k is None or k<201: continue
            for r in ("breakout","trend"):
                if fires(r,X[s],k): pend.append((s,r,X[s]["mom126"][k] or 0))
        pend=[(s,r) for s,r,m in sorted(pend,key=lambda z:-z[2])]
        eq=cash+sum(p["q"]*p["last"] for p in sat);peak=max(peak,eq);mdd=max(mdd,1-eq/peak)
        if curve is not None: curve.append((t,eq))
    return eq,mdd,n
P=[("2020-2022",dt.datetime(2020,1,1),dt.datetime(2022,12,31,23)),("2023-Sep2026",dt.datetime(2023,1,1),dt.datetime(2026,9,30)),("last 12mo",dt.datetime(2025,10,1),dt.datetime(2026,10,7))]
V=[("D  daily (live now)",dict(iv="1d")),("4A 4h, same stops",dict(iv="4h",holdmul=6)),("4B 4h, vol-scaled stops",dict(iv="4h",scale=0.41))]
res={}
for lab,a,b in P:
    print(lab)
    for n,kw in V:
        e,m,t=run(a=a,b=b,**kw);res[(lab,n)]=e;print(f"  {n:26s} $100->${e:7.1f}  worst drop {100*m:3.0f}%  trades {t}")
json.dump({f"{k[0]}|{k[1]}":v for k,v in res.items()},open("res.json","w"))
