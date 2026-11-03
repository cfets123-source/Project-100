"""Our bot on cheap static-drawdown challenges: multi-phase targets, static max loss, daily loss on day start."""
import datetime as dt, statistics as st, sys
import tp as T
from noise import vol_scale
days = T.load(sys.argv[1]); keys = sorted(days); unit = {}
for i, d in enumerate(keys):
    hist = [days[k] for k in keys[max(0, i - 20):i]]
    if len(hist) < 15: continue
    p = T.day(hist, days[d], 1, tp=300); s = vol_scale(hist)
    unit[d] = {k: [x * s / T.PER for x in p[k]] for k in ("c", "x", "w")}; unit[d]["end"] = p["end"] * s / T.PER
def phase(seq, lev, tgt, mx, daily, mind, start_i):
    bal, traded, i = 0.0, 0, start_i
    stop = 0.75 * daily
    while i < len(seq) and i - start_i < 126:
        p = seq[i]; i += 1; pnl = p["end"] * lev
        for c, x, w in zip(p["c"], p["x"], p["w"]):
            if bal + w * lev <= -mx or w * lev <= -daily: return False, i
            if c * lev <= -stop or bal + c * lev <= -mx + 0.012: pnl = x * lev; break
            if bal + c * lev >= tgt and traded >= mind - 1: pnl = x * lev; break
        bal += pnl; traded += abs(p["end"]) > 1e-12
        if bal <= -mx: return False, i
        if bal >= tgt and traded >= mind: return True, i
    return False, i
def challenge(seq, s, lev, phases):
    i = s
    for tgt, mx, daily, mind in phases:
        ok, i = phase(seq, lev, tgt, mx, daily, mind, i)
        if not ok: return False, i - s
    return True, i - s
FIRMS = {"Eightcap 1-step ($69, ~$55 w/ code)": [(0.10, 0.08, 0.04, 5)],
         "Goat Funded 2-step 5K ($33)": [(0.10, 0.10, 0.05, 3), (0.05, 0.10, 0.05, 3)],
         "Maven 2-step 2K ($19)": [(0.08, 0.08, 0.04, 3), (0.05, 0.08, 0.04, 3)],
         "Maven 3-step 2K ($13)": [(0.03, 0.03, 0.02, 3)] * 3}
ks = sorted(unit)
for name, ph in FIRMS.items():
    for lev in (2, 3, 4):
        row = []
        for rg in (lambda q: q <= dt.date(2023, 12, 29), lambda q: q >= dt.date(2024, 1, 2)):
            seq = [unit[q] for q in ks if rg(q)]
            r = [challenge(seq, s, lev, ph) for s in range(0, len(seq) - 260, 2)]
            ps = [d for o, d in r if o]
            row.append("pass %2.0f%% ~%3sd" % (100 * len(ps) / len(r), int(st.median(ps)) if ps else "-"))
        print("%-38s %dx  2019-23: %s | 2024-26: %s" % (name, lev, row[0], row[1]), flush=True)
