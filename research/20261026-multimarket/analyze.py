"""Score SPY/IWM/GLD NOISE paths vs QQQ: standalone stats, correlation, prop EV (scaled to MNQ-equivalent risk),
and combined portfolios (same total risk budget split equally across markets)."""
import datetime as dt, os, pickle, statistics as st, sys
import numpy as np
L = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "20261022-ladder")
sys.path.insert(0, L); sys.path.insert(0, os.path.join(L, "..", "..", "prop"))
import variants as V
P = {"QQQ": pickle.load(open('/home/claude/data/qqq/v_hourly+vt1.0.pkl', 'rb'))}
for s in ("SPY", "IWM", "GLD"):
    P[s] = pickle.load(open('/home/claude/data/multi/v_%s.pkl' % s, 'rb'))
# contract notional ($, Oct 2026) relative to one MNQ (~$58k): MES ~$38k, M2K ~$14k, MGC ~$40k
NOTIONAL = {"QQQ": 1.0, "SPY": 38000 / 58000, "IWM": 14000 / 58000, "GLD": 40000 / 58000}
DEV = (dt.date(2019, 1, 1), dt.date(2023, 12, 29)); CONF = (dt.date(2024, 1, 2), dt.date(2026, 9, 30))
common = sorted(set.intersection(*[set(p) for p in P.values()]))
inn = lambda ks, r: [k for k in ks if r[0] <= k <= r[1]]
ret = lambda p, k: p[k]["end"] * p[k]["scale"]

def stats(sym, ks):
    r = np.array([ret(P[sym], k) for k in ks]) * 1e4
    return "%6.2fbp/day  Sharpe %5.2f  win %4.1f%%" % (r.mean(), r.mean() / r.std() * 252 ** .5, 100 * (r > 0).mean())

print("== standalone (unit = 1x notional, vol-scaled) ==")
for s in P:
    for nm, rg in (("DEV", DEV), ("CONF", CONF)):
        print("%-4s %-4s %s" % (s, nm, stats(s, inn(common, rg))))
print("\n== daily return correlation with QQQ ==")
for s in ("SPY", "IWM", "GLD"):
    for nm, rg in (("DEV", DEV), ("CONF", CONF)):
        ks = inn(common, rg)
        print("%-4s %-4s %.2f" % (s, nm, np.corrcoef([ret(P["QQQ"], k) for k in ks], [ret(P[s], k) for k in ks])[0, 1]))

def scaled(sym):
    f = NOTIONAL[sym]
    return {k: dict(v, c=[a * f for a in v["c"]], x=[a * f for a in v["x"]], w=[a * f for a in v["w"]], end=v["end"] * f)
            for k, v in P[sym].items()}

def blend(syms, ks):
    """Same total contracts split across markets; vol scale applied per market inside the path."""
    out = {}
    for k in ks:
        ps = [P[s][k] for s in syms]; f = 1.0 / len(syms)
        n = min(len(p["c"]) for p in ps)
        g = lambda key: [f * sum(p[key][i] * p["scale"] for p in ps) for i in range(n)]
        c, x, w = g("c"), g("x"), g("w")
        out[k] = {"c": c, "x": x, "w": w, "end": c[-1], "flat": all(abs(e) < 1e-12 for e in c), "scale": 1.0}
    return out

print("\n== prop EV per 50K Topstep attempt (risk scaled to MNQ-equivalent) ==")
rows = [(s, scaled(s)) for s in P] + [
    ("QQQ+SPY", blend(["QQQ", "SPY"], common)), ("QQQ+IWM", blend(["QQQ", "IWM"], common)),
    ("QQQ+GLD", blend(["QQQ", "GLD"], common)), ("QQQ+SPY+IWM+GLD", blend(["QQQ", "SPY", "IWM", "GLD"], common))]
for nm, pd in rows:
    ks = sorted(set(pd) & set(common))
    if nm in ("QQQ+SPY", "QQQ+IWM", "QQQ+GLD", "QQQ+SPY+IWM+GLD"):
        r = np.array([pd[k]["end"] for k in inn(ks, CONF)]) * 1e4
        print("   %s CONF combined %.2fbp/day Sharpe %.2f" % (nm, r.mean(), r.mean() / r.std() * 252 ** .5))
    print(V.score(pd, inn(ks, DEV), nm + " DEV")[0]); print(V.score(pd, inn(ks, CONF), nm + " CONF")[0], flush=True)
