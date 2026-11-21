"""False-breakout guardrails, tested from today's account position (bal -631.30, best day 273.12, MLL locked floor 48,066.84).
Live rules = NOISE hourly, vol sizing, TP $600, $800 stop. Each variant changes ONE thing."""
import datetime as dt, statistics as st, sys
import noise, tp as T
orig = noise.decide
from noise import LAST, OPEN, sigma, vwap

def k_band(k):
    def d(h, td, t, pos):
        if not noise.is_check(t) or t not in td or OPEN not in td or not h: return None
        pc = h[-1].get(LAST, (None,) * 4)[3]; s = sigma(h, t)
        if pc is None or s is None: return None
        op, c = td[OPEN][0], td[t][3]; up, dn = max(op, pc) * (1 + k * s), min(op, pc) * (1 - k * s); vw = vwap(td, t)
        tg = pos
        if pos > 0 and c < max(max(op, pc) * (1 + s), vw): tg = 0      # exits unchanged (k=1 band)
        elif pos < 0 and c > min(min(op, pc) * (1 - s), vw): tg = 0
        if tg == 0: tg = 1 if c > up else -1 if c < dn else 0
        return tg
    return d

def confirm():
    """Enter only if the previous hourly check was already beyond the band in the same direction."""
    def d(h, td, t, pos):
        tg = orig(h, td, t, pos)
        if tg and tg != pos and not pos:
            prev = [x for x in sorted(td) if x < t and noise.is_check(x)]
            if not prev or orig(h, td, prev[-1], 0) != tg: return None
        return tg
    return d

def trend(n=20):
    """Longs only above the 20-day average close, shorts only below."""
    def d(h, td, t, pos):
        tg = orig(h, td, t, pos)
        if tg and tg != pos:
            ma = sum(x[LAST][3] for x in h[-n:] if LAST in x) / max(1, len([x for x in h[-n:] if LAST in x]))
            c = td[t][3]
            if (tg > 0 and c < ma) or (tg < 0 and c > ma): return 0 if pos else None
        return tg
    return d

days = T.load(sys.argv[1])
tests = [("live rules", orig), ("bigger breakout k=1.2", k_band(1.2)), ("bigger breakout k=1.5", k_band(1.5)),
         ("2-check confirmation", confirm()), ("20-day trend filter", trend())]
for nm, fn in tests:
    T.decide = fn; pd = T.build(days, tp=600); ks = sorted(pd); out = []
    for rg in (lambda q: q <= dt.date(2023, 12, 29), lambda q: q >= dt.date(2024, 1, 2)):
        seq = [pd[q] for q in ks if rg(q)]
        tr = [p for p in seq if any(abs(c) > 1e-9 for c in p["c"])]
        lose = sum(p["end"] < 0 for p in tr) / len(tr)
        r = [T.combine(seq[s:], -631.30, 66.84, 273.12) for s in range(0, len(seq) - 130)]
        ps = [d for o, d in r if o == "pass"]
        out.append("losing trade-days %2.0f%%  $/day %3.0f  pass %2.0f%%" % (100 * lose, st.mean(p["end"] for p in seq), 100 * len(ps) / len(r)))
    print("%-24s 2019-23: %s | 2024-26: %s" % (nm, out[0], out[1]), flush=True)
