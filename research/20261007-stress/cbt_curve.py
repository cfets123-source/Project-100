from scan_bt import *
C=.0005
SY=[s for s in sorted(CRYPTO) if s in DATA]
0 and print(SY, {s:(DATA[s][0][0],len(DATA[s])) for s in SY})
CL={s:{r[0]:(k,r) for k,r in enumerate(DATA[s])} for s in SY}
days=sorted(set(d for s in SY for d in CL[s]))
SIG={}
for s in SY:
    rows,x=DATA[s],IND[s]
    for r in ('breakout','trend'):
        for i in range(201,len(rows)-1):
            if RULES[r]['entry'](x,i): SIG.setdefault(rows[i+1][0],[]).append((s,r,x['mom126'][i] or 0))
CURVE=[]
def signals_run(a,b,slots=3):
    CURVE.clear();cash=100.0;sat=[];peak=100;mdd=0;n=0
    for d in [d for d in days if a<=d<=b]:
        for p in list(sat):
            z=CL[p['s']].get(d)
            if not z: continue
            k,(dd,o,h,l,c,_)=z;px=None
            if p['x']: px=o
            elif l<=p['stop']: px=min(o,p['stop'])
            elif h>=p['tgt']: px=max(o,p['tgt'])
            if px: cash+=p['q']*px*(1-C);sat.remove(p);continue
            p['last']=c;p['n']+=1;R=RULES[p['r']]
            if p['n']>=R['hold'] or R['exit'](IND[p['s']],k): p['x']=True
        eq=cash+sum(p['q']*p['last'] for p in sat)
        held={p['s'] for p in sat}
        for s,r,m in sorted(SIG.get(d,[]),key=lambda z:-z[2]):
            if s in held or len(sat)>=slots: continue
            st=min(cash,eq/slots)
            if st<1: break
            po=CL[s][d][1][1]*(1+C);R=RULES[r]
            sat.append(dict(s=s,r=r,q=st/po,stop=po*(1-R['stop']),tgt=po*(1+R['target']),n=0,last=po,x=False));cash-=st;held.add(s);n+=1
        eq=cash+sum(p['q']*p['last'] for p in sat);peak=max(peak,eq);mdd=max(mdd,1-eq/peak);CURVE.append((d,eq))
    return eq,mdd,n
def trend_run(a,b,sma=200,syms=None):
    syms=syms or SY;cash=100.0;hold={};peak=100;mdd=0;n=0
    for d in [d for d in days if a<=d<=b]:
        live=[s for s in syms if d in CL[s] and CL[s][d][0]>sma]
        eq=cash+sum(q*CL[s][d][1][4] for s,q in hold.items() if d in CL[s])
        for s in live:
            k,(dd,o,h,l,c,_)=CL[s][d];x=IND[s];ma=sum(x['c'][k-sma:k])/sma;prev=x['c'][k-1]
            if s in hold and prev<ma: cash+=hold.pop(s)*o*(1-C);n+=1
            elif s not in hold and prev>ma:
                st=min(cash,eq/len(syms))
                if st>1: hold[s]=st/(o*(1+C));cash-=st;n+=1
        eq=cash+sum(q*CL[s][d][1][4] for s,q in hold.items() if d in CL[s]);peak=max(peak,eq);mdd=max(mdd,1-eq/peak)
    return eq,mdd,n
def bh(a,b,s='BTC-USD'):
    ds=[d for d in days if a<=d<=b and d in CL[s]];p0=CL[s][ds[0]][1][1];peak=0;mdd=0
    for d in ds:
        v=CL[s][d][1][4]/p0;peak=max(peak,v);mdd=max(mdd,1-v/peak)
    return 100*CL[s][ds[-1]][1][4]/p0,mdd,1
