import sys, datetime as dt
sys.path.insert(0,'/home/claude/sr/mm')
from scan_bt import load
P=[("2011-2020",dt.date(2011,1,3),dt.date(2020,12,31)),("2021-Sep2026",dt.date(2021,1,4),dt.date(2026,9,25)),("last 12mo",dt.date(2025,10,1),dt.date(2026,9,25))]
def stats(rs):
    eq=100;peak=100;mdd=0
    for r in rs: eq*=1+r;peak=max(peak,eq);mdd=max(mdd,1-eq/peak)
    return eq,mdd
for s in ("SPY","QQQ","TQQQ"):
    rows=load(s); print(s)
    for lab,a,b in P:
        R=[r for r in rows if a<=r[0]<=b]
        bh=[R[i][4]/R[i-1][4]-1 for i in range(1,len(R))]
        out=[]
        for name,c,kind in [("buy & hold",0,"bh"),("overnight 0.03%/side",.0003,"on"),("overnight 0.01%/side",.0001,"on"),("intraday 0.03%/side",.0003,"id")]:
            if kind=="bh": rs=bh
            elif kind=="on": rs=[(R[i][1]/R[i-1][4])*(1-c)/(1+c)-1 for i in range(1,len(R))]
            else: rs=[(R[i][4]/R[i][1])*(1-c)/(1+c)-1 for i in range(1,len(R))]
            e,m=stats(rs); out.append(f"{name}: ${e:,.0f} ({100*m:.0f}% drop, ratio {((e/100)-1)/m if m else 0:.2f})")
        print(f"  {lab:13s} | "+" | ".join(out))
