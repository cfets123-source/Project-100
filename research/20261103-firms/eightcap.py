"""Our NOISE bot (live rules, TP at the same % move) on an Eightcap-style one-phase challenge:
target +10%, max loss 8% of the starting balance (static), daily loss 4%, min 5 trading days. Sized as notional = lev x account."""
import datetime as dt, statistics as st, sys
import tp as T
from noise import vol_scale
days = T.load(sys.argv[1]); keys = sorted(days); unit = {}
for i, d in enumerate(keys):
    hist = [days[k] for k in keys[max(0, i - 20):i]]
    if len(hist) < 15: continue
    p = T.day(hist, days[d], 1, tp=300)                       # 1 MNQ-notional; TP = same 0.52% move as live
    s = vol_scale(hist)
    unit[d] = {k: [x * s / T.PER for x in p[k]] for k in ("c", "x", "w")}
    unit[d]["end"] = p["end"] * s / T.PER
def challenge(seq, lev, stop_frac=0.03, maxd=126):
    bal, traded = 0.0, 0
    for i, p in enumerate(seq[:maxd], 1):
        pnl = p["end"] * lev
        for c, x, w in zip(p["c"], p["x"], p["w"]):
            if bal + w * lev <= -0.08 or w * lev <= -0.04: return "fail", i
            if c * lev <= -stop_frac or bal + c * lev <= -0.08 + 0.01: pnl = x * lev; break
            if bal + c * lev >= 0.10 and traded >= 4: pnl = x * lev; break
        bal += pnl; traded += abs(p["end"]) > 1e-12
        if bal <= -0.08: return "fail", i
        if bal >= 0.10 and traded >= 5: return "pass", i
    return "timeout", maxd
ks = sorted(unit)
for lev in (1, 2, 3, 4, 6):
    row = []
    for rg in (lambda q: q <= dt.date(2023, 12, 29), lambda q: q >= dt.date(2024, 1, 2)):
        seq = [unit[q] for q in ks if rg(q)]
        r = [challenge(seq[s:], lev) for s in range(0, len(seq) - 130)]
        ps = [d for o, d in r if o == "pass"]
        row.append("pass %2.0f%% ~%3sd" % (100 * len(ps) / len(r), int(st.median(ps)) if ps else "-"))
    print("notional %dx account   2019-23: %s | 2024-26: %s" % (lev, row[0], row[1]), flush=True)
