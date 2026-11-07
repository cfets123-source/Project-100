"""Entries stay hourly (:55 bars); EXIT checks run more often (every 5/15/30 min) or add one late exit check."""
import datetime as dt, statistics as st, sys
import noise, tp as T
def make(exit_minutes):
    def decide(history, today, t, position):
        hourly = t.minute == 55 and dt.time(9, 55) <= t <= dt.time(15, 25)
        exit_chk = position != 0 and t.minute in exit_minutes and dt.time(9, 55) <= t <= dt.time(15, 50)
        if not (hourly or exit_chk) or t not in today or noise.OPEN not in today or not history: return None
        pc = history[-1].get(noise.LAST, (None,) * 4)[3]; s = noise.sigma(history, t)
        if pc is None or s is None: return None
        op, c = today[noise.OPEN][0], today[t][3]
        up, dn = max(op, pc) * (1 + s), min(op, pc) * (1 - s); vw = noise.vwap(today, t); tg = position
        if position > 0 and c < max(up, vw): tg = 0
        elif position < 0 and c > min(dn, vw): tg = 0
        if tg == 0 and hourly: tg = 1 if c > up else -1 if c < dn else 0
        return tg
    return decide
days = T.load(sys.argv[1])
for nm, mins in (("live: exits hourly", ()), ("exits every 30 min", (25, 55)), ("exits every 15 min", (10, 25, 40, 55)),
                 ("exits every 5 min", tuple(range(0, 60, 5))), ("+ one late exit check 3:25", "late")):
    if mins == "late":
        base = make(()); late = make((25,))
        T.decide = lambda h, td, t, p: (late(h, td, t, p) if t == dt.time(15, 25) else base(h, td, t, p))
    else:
        T.decide = make(mins)
    pd = T.build(days, tp=600); ks = sorted(pd); out = []
    for rg in (lambda q: q <= dt.date(2023, 12, 29), lambda q: q >= dt.date(2024, 1, 2)):
        seq = [pd[q] for q in ks if rg(q)]
        r = [T.combine(seq[s:], -503.08, 66.84, 273.12) for s in range(0, len(seq) - 130)]
        ps = [d for o, d in r if o == "pass"]
        out.append("$/day %3.0f  pass %2.0f%% ~%2dd" % (st.mean(p["end"] for p in seq), 100 * len(ps) / len(r), st.median(ps)))
    print("%-28s 2019-23: %s | 2024-26: %s" % (nm, out[0], out[1]), flush=True)
