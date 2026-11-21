from scan_bt import *
CL={s:{r[0]:(k,r) for k,r in enumerate(DATA[s])} for s in DATA}
T={r[0]:r for r in DATA['TQQQ']}; Q=IND['QQQ']; qd={r[0]:k for k,r in enumerate(DATA['QQQ'])}
GR=['large stocks','index/sector ETF','leveraged ETF','bonds/commod/intl']
SYMS=[s for g in GR for s in GROUPS[g] if s in DATA]
SIG={}
for s in SYMS:
    rows,x=DATA[s],IND[s]
    for r in ('breakout','trend'):
        for i in range(201,len(rows)-1):
            if RULES[r]['entry'](x,i): SIG.setdefault(rows[i+1][0],[]).append((s,r,x['mom126'][i] or 0))
C=.0005
def run(a,b,mode='none',margin=.2,profit_only=False,weekly=False,core=.5,slots=5):
    days=sorted(d for d in T if a<=d<=b); cash=100.0; csh=0; ce=0; pend=False; sat=[]; peak=100; mdd=0; rot=0; ntr=0
    def mark(p,d):
        z=CL[p['s']].get(d); return z[1][4] if z else p['last']
    for d in days:
        o,h,l,c=T[d][1],T[d][2],T[d][3],T[d][4]
        # satellite exits
        for p in list(sat):
            z=CL[p['s']].get(d)
            if not z: continue
            k,(dd,po,ph,pl,pc,_)=z; px=None
            if p['exit_next']: px=po
            elif pl<=p['stop']: px=min(po,p['stop'])
            elif ph>=p['tgt']: px=max(po,p['tgt'])
            if px is not None: cash+=p['q']*px*(1-C); sat.remove(p); continue
            p['last']=pc; p['n']+=1; R=RULES[p['r']]
            if p['n']>=R['hold'] or R['exit'](IND[p['s']],k): p['exit_next']=True
        eq=cash+csh*c+sum(p['q']*mark(p,d) for p in sat)
        if pend and csh==0: st=min(cash,eq*core); csh=st/(o*(1+C)); cash-=st; ce=o*(1+C)
        pend=False
        if csh>0:
            if l<=ce*.75: cash+=csh*min(o,ce*.75)*(1-C); csh=0
            elif h>=ce*1.5: cash+=csh*max(o,ce*1.5)*(1-C); csh=0
        k=qd.get(d)
        if k and Q['s200'][k] and csh==0 and Q['c'][k]>Q['s200'][k]: pend=True
        held={p['s'] for p in sat}
        cands=sorted([z for z in SIG.get(d,[]) if z[0] not in held and d in CL[z[0]]],key=lambda z:-z[2]); seen=set()
        for s,r,m in cands:
            if s in seen: continue
            seen.add(s)
            if len(sat)>=slots:
                if mode=='none' or (weekly and d.weekday()!=0): continue
                def cur_mom(p):
                    z=CL[p['s']].get(d); return (IND[p['s']]['mom126'][z[0]-1] or 0) if z else 9
                pool=[p for p in sat if not p['exit_next'] and (not profit_only or mark(p,d)>p['e'])]
                if not pool: continue
                w=min(pool,key=cur_mom)
                if m < cur_mom(w)+margin: continue
                zz=CL[w['s']][d]; cash+=w['q']*zz[1][1]*(1-C); sat.remove(w); rot+=1
            eq=cash+csh*c+sum(p['q']*mark(p,d) for p in sat)
            st=min(cash,eq*(1-core)/slots)
            if st<1: break
            po=CL[s][d][1][1]*(1+C); R=RULES[r]
            sat.append(dict(s=s,r=r,q=st/po,e=po,stop=po*(1-R['stop']),tgt=po*(1+R['target']),n=0,last=po,exit_next=False)); cash-=st; ntr+=1
        eq=cash+csh*c+sum(p['q']*mark(p,d) for p in sat); peak=max(peak,eq); mdd=max(mdd,1-eq/peak)
    return eq,mdd,ntr,rot
P=[('2011-2020',dt.date(2011,1,3),dt.date(2020,12,31)),('2021-Sep26',dt.date(2021,1,4),dt.date(2026,9,25)),('last 12mo',dt.date(2025,10,1),dt.date(2026,9,25))]
V=[('Current: hold to stop/target/time',dict()),
   ('Rotate daily, any position, +10pt better',dict(mode='rot',margin=.1)),
   ('Rotate daily, any position, +30pt better',dict(mode='rot',margin=.3)),
   ('Rotate daily, only winners, +10pt',dict(mode='rot',margin=.1,profit_only=True)),
   ('Rotate weekly (Mon), any, +20pt',dict(mode='rot',margin=.2,weekly=True)),
   ('Rotate weekly (Mon), only winners, +20pt',dict(mode='rot',margin=.2,weekly=True,profit_only=True))]
for lab,a,b in P:
    print(lab)
    for n,kw in V:
        e,m,t,r=run(a,b,**kw); print(f"  {n:44s} $100->${e:6.0f}  worst drop {100*m:3.0f}%  buys {t:4d}  rotations {r:4d}")
