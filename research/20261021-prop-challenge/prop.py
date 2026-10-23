import datetime as dt, statistics as st
from scan_bt import DATA, IND
Q=DATA['QQQ']; X=IND['QQQ']
FEE=95; COST=0.0004  # per side incl. slippage, as fraction of notional (approx $1.5 + 1 tick on ~$55k)
def pos(rule,i):
    if rule=='S0': return 1
    if rule=='S1': return 1 if X['s200'][i] and X['c'][i]>X['s200'][i] else 0
    if rule=='S2': return 1 if X['s200'][i] and X['s50'][i] and X['s50'][i]>X['s200'][i] else 0
def path(rule, size, start, maxd, mode):
    bal=50000.0; hw=50000.0; lock=False; inpos=0; paid=0.0; n=0
    floor=48000.0
    for i in range(start, min(start+maxd, len(Q)-1)):
        want=pos(rule,i-1)  # decided on prior close, held today
        d,o,h,l,c,_=Q[i]; pc=Q[i-1][4]
        notional=50000*size
        if want!=inpos: bal-=notional*COST; inpos=want
        if inpos:
            worst=bal+notional*(l/pc-1); bal+=notional*(c/pc-1)
            if worst<=floor or (pc-l)/pc*notional>=1000: return ('fail',i-start+1,paid)
        n+=1
        if bal>hw: hw=bal
        if mode=='eval':
            if bal>=53000: return ('pass',n,0)
            floor=min(50000, hw-2000) if not lock else 50000
            if floor>=50000: lock=True
        else:
            floor=50000 if lock else max(48000, hw-2000)
            if hw-2000>=50000: lock=True; floor=50000
            if bal>=52000 and lock:
                paid+=2000*0.9; bal-=2000; hw=bal
    return ('timeout',n,paid)
starts=[k for k,r in enumerate(Q) if dt.date(2011,1,3)<=r[0]<=dt.date(2026,8,31) and k>201]
print(f"{'rule':4} {'size':>4} {'pass%':>6} {'medDays':>7} {'cost/pass':>9} {'funded payout':>13} {'net/attempt':>11}")
for rule in ('S0','S1','S2'):
    for size in (0.5,1,2):
        res=[path(rule,size,s,90,'eval') for s in starts[::3]]
        p=[r for r in res if r[0]=='pass']; rate=len(p)/len(res)
        days=st.median([r[1] for r in p]) if p else 0
        months=st.mean([1+(r[1]>30)+(r[1]>60) for r in res])
        cost=FEE*months/rate if rate else float('inf')
        pays=[path(rule,size,s+r[1],250,'funded')[2] for s,r in zip(starts[::3],res) if r[0]=='pass' and s+r[1]<len(Q)-260]
        avgpay=st.mean(pays) if pays else 0
        print(f"{rule:4} {size:>4} {rate:6.1%} {days:7.0f} {cost:9.0f} {avgpay:13.0f} {rate*avgpay-FEE*months:11.0f}")
