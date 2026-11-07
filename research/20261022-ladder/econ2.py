"""Funded-account policy search: dynamic contracts by cushion, bot buffer, payout cushion, payout path."""
import statistics as st, sys
sys.path.insert(0, '.')
import ladder as L

def xfa(seq, T, per=1500, nmax=2, buffer=150, cushion=1500, path="standard", maxd=504):
    bal = hw = 0.0; locked = paid = False; wins = 0; got = 0.0; npay = 0; since = []; days_since = 0
    for i, p in enumerate(seq[:maxd], 1):
        floor = 0.0 if (locked or paid) else min(0.0, hw - T["mll"])
        room = bal - floor
        n = max(1, min(nmax, int(room // per)))
        pnl, breach, near = L.day_pnl(p, n, room, 400 * n, None, buffer, T["dll"], bal)
        bal += pnl
        if breach or near: return got, npay, i, "fail"
        hw = max(hw, bal); locked = locked or hw - T["mll"] >= 0
        days_since += 1; since.append(pnl)
        if pnl >= 150: wins += 1
        if path == "standard":
            ok, cap = wins >= 5, T["cap"]
        else:  # consistency path: 3+ days, best day <= 40% of the period's profit
            prof = sum(since)
            ok, cap = days_since >= 3 and prof > 0 and max(since) <= 0.4 * prof, 3000
        if ok:
            amt = min(0.5 * bal, cap, bal - cushion)
            if amt >= 125:
                bal -= amt; got += amt * L.SPLIT; npay += 1; wins = 0; paid = True; hw = bal; since = []; days_since = 0
    return got, npay, maxd, "alive"

days = L.load('/home/claude/data/qqq/noise_days.pkl'); keys = sorted(days); seq = [days[k] for k in keys]
T = L.TYPES[50]; xs = range(0, len(seq) - 510, 3)
print("per  nmax buf  cushion path         avg$   med$   p25$  p(any)  life  alive2y  $/month-alive")
rows = []
for path in ("standard", "consistency"):
    for per in (1000, 1500, 2500):
        for nmax in (1, 2, 3):
            for cush in (1000, 2000, 3000):
                for buf in (150,):
                    r = [xfa(seq[s:], T, per, nmax, buf, cush, path) for s in xs]
                    g = sorted(x[0] for x in r)
                    life = st.mean(x[2] for x in r)
                    rows.append((st.mean(g), per, nmax, buf, cush, path, st.median(g), g[len(g)//4], sum(x[1] > 0 for x in r)/len(r), st.median(x[2] for x in r), sum(x[3]=="alive" for x in r)/len(r), st.mean(g)/(life/21)))
for row in sorted(rows, reverse=True)[:14]:
    a, per, nmax, buf, cush, path, med, p25, pany, life, alive, pm = row
    print("%4d  %d   %3d  %5d  %-11s %6.0f %6.0f %6.0f  %5.1f%%  %4.0f  %5.1f%%   %5.0f" % (per, nmax, buf, cush, path, a, med, p25, 100*pany, life, 100*alive, pm))
