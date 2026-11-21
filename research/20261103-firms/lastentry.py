"""No NEW entries after a cutoff hour (exits/holds unchanged). Live rules otherwise (TP $600)."""
import datetime as dt, statistics as st, sys
import noise, tp as T
orig = noise.decide
def make(last_entry):
    def decide(history, today, t, position):
        tg = orig(history, today, t, position)
        if tg and tg != position and t > last_entry:    # would open/reverse late: stay/go flat instead
            return 0 if position else None
        return tg
    return decide
days = T.load(sys.argv[1])
for nm, cut in (("live: entries until 3:00", dt.time(14, 55)), ("no entries at 3:00", dt.time(13, 55)),
                ("no entries after 1:00", dt.time(12, 55))):
    T.decide = make(cut); pd = T.build(days, tp=600); ks = sorted(pd); out = []
    for rg in (lambda q: q <= dt.date(2023, 12, 29), lambda q: q >= dt.date(2024, 1, 2)):
        seq = [pd[q] for q in ks if rg(q)]
        r = [T.combine(seq[s:], -503.08, 66.84, 273.12) for s in range(0, len(seq) - 130)]
        ps = [d for o, d in r if o == "pass"]
        out.append("$/day %3.0f  pass %2.0f%% ~%2dd" % (st.mean(p["end"] for p in seq), 100 * len(ps) / len(r), st.median(ps)))
    print("%-26s 2019-23: %s | 2024-26: %s" % (nm, out[0], out[1]), flush=True)
