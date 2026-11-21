"""Ways to trade more often: lower breakout band (k), 30-minute checks. Live rules otherwise (TP $600)."""
import datetime as dt, statistics as st, sys
import noise, tp as T
orig = noise.decide
def make(k=1.0, half=False):
    def is_check(t): return t.minute in ((25, 55) if half else (55,)) and dt.time(9, 55) <= t <= dt.time(15, 25)
    def decide(history, today, t, position):
        if not is_check(t) or t not in today or noise.OPEN not in today or not history: return None
        pc = history[-1].get(noise.LAST, (None,) * 4)[3]; s = noise.sigma(history, t)
        if pc is None or s is None: return None
        op, c = today[noise.OPEN][0], today[t][3]
        up, dn = max(op, pc) * (1 + k * s), min(op, pc) * (1 - k * s); vw = noise.vwap(today, t); tg = position
        if position > 0 and c < max(up, vw): tg = 0
        elif position < 0 and c > min(dn, vw): tg = 0
        if tg == 0: tg = 1 if c > up else -1 if c < dn else 0
        return tg
    return decide
days = T.load(sys.argv[1])
for nm, kw in (("live (k=1.0, hourly)", {}), ("k=0.8 hourly", {"k": 0.8}), ("k=0.6 hourly", {"k": 0.6}),
               ("k=1.0, 30-min checks", {"half": True}), ("k=0.8, 30-min checks", {"k": 0.8, "half": True})):
    T.decide = make(**kw); pd = T.build(days, tp=600); ks = sorted(pd); out = []
    for rg in (lambda q: q <= dt.date(2023, 12, 29), lambda q: q >= dt.date(2024, 1, 2)):
        seq = [pd[q] for q in ks if rg(q)]
        tdays = 100 * sum(any(abs(c) > 1e-9 for c in p["c"]) for p in seq) / len(seq)
        r = [T.combine(seq[s:], -166.20, 66.84, 273.12) for s in range(0, len(seq) - 130)]
        ps = [d for o, d in r if o == "pass"]
        out.append("trade days %2.0f%%  $/day %3.0f  pass %2.0f%% ~%2dd" % (tdays, st.mean(p["end"] for p in seq), 100 * len(ps) / len(r), st.median(ps)))
    print("%-22s 2019-23: %s | 2024-26: %s" % (nm, out[0], out[1]), flush=True)
