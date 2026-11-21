"""NOISE (live rules: hourly, 1% vol sizing, TP $600) on other futures proxies, sized to MNQ-equivalent notional.
A market qualifies only if it is positive and passes Combines in BOTH 2019-23 and 2024-26."""
import datetime as dt, sys
import numpy as np
import tp as T
d0, d1 = dt.date(2023, 12, 29), dt.date(2024, 1, 2)
q = T.build(T.load('/home/claude/dl/QQQ_5m.csv.gz'), tp=600)
for sym in sys.argv[1:]:
    pd = T.build(T.load('/home/claude/dl/more/%s_5m.csv.gz' % sym), tp=600); ks = sorted(pd)
    if len(ks) < 600:
        print(sym, "too few full sessions:", len(ks)); continue
    common = [k for k in ks if k in q]
    for nm, sel in (("DEV ", [k for k in ks if k <= d0]), ("CONF", [k for k in ks if k >= d1])):
        e = np.array([pd[k]["end"] for k in sel]); c = [k for k in common if k in set(sel)]
        corr = np.corrcoef([q[k]["end"] for k in c], [pd[k]["end"] for k in c])[0, 1]
        print("%-4s %s Sharpe %5.2f corr-w-MNQ %5.2f  %s" % (sym, nm, e.mean() / e.std() * 252 ** .5, corr, T.score(pd, sel)), flush=True)
