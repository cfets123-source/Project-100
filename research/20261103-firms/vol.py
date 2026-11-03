"""Volume filter test: new entries only when today's relative volume (cumulative volume so far vs the average of the
same time of day over the last 14 days) is at least k. Exits are unchanged. Baseline = live rules (TP $600)."""
import datetime as dt, sys
import tp as T
from noise import LAST, decide, vol_scale

def cumvol(day):
    out, s = {}, 0.0
    for t in sorted(day):
        s += day[t][4]; out[t] = s
    return out

def day(history, today, n, k=None, hi=None, tp=600):
    S = n * T.PER; times = sorted(today); pos, entry, real = 0, None, 0.0; pend = None
    cv = cumvol(today); hcv = [cumvol(d) for d in history[-14:]]
    c, x, w = [], [], []
    for i, t in enumerate(times):
        o, h, l, cl, v = today[t]
        if pend is not None:
            if pend != pos:
                if pos: real += S * (pos * (o / entry - 1) - T.COST); pos = 0
                if pend: pos, entry = pend, o; real -= S * T.COST
            pend = None
        if t == LAST:
            if pos: real += S * (pos * (o / entry - 1) - T.COST); pos = 0
            c.append(real); x.append(real); w.append(real); break
        op = lambda px: S * (pos * (px / entry - 1) - T.COST) if pos else 0.0
        w.append(real + op(l if pos > 0 else h))
        if pos and tp:
            lvl = entry * (1 + pos * tp / S); pen = lvl * 0.00002 * pos
            if (pos > 0 and h >= lvl + pen) or (pos < 0 and l <= lvl + pen):
                real += S * (pos * (lvl / entry - 1) - T.COST); pos = 0
        c.append(real + op(cl))
        nxt = today[times[i + 1]][0] if i + 1 < len(times) else cl
        tg = decide(history, today, t, pos)
        if tg and tg != pos and (k or hi):                 # a new entry (or reversal): check relative volume
            base = [d[t] for d in hcv if t in d]
            rv = cv[t] / (sum(base) / len(base)) if base else 1.0
            if (k and rv < k) or (hi and rv > hi):
                tg = 0 if pos else None
        if tg is not None and tg != pos: pend = tg
        x.append(real + op(nxt))
    return {"c": c, "x": x, "w": w, "end": c[-1]}

def build(days, **kw):
    keys = sorted(days); out = {}
    for i, d in enumerate(keys):
        hist = [days[q] for q in keys[max(0, i - 20):i]]
        if len(hist) < 15: continue
        out[d] = day(hist, days[d], max(1, int(round(2 * vol_scale(hist)))), **kw)
    return out

days = T.load(sys.argv[1])
for name, kw in [("skip > 1.3x", {"hi": 1.3}), ("skip > 1.8x", {"hi": 1.8}), ("skip > 2.2x", {"hi": 2.2})]:
    pd = build(days, **kw); ks = sorted(pd)
    dev = [q for q in ks if q <= dt.date(2023, 12, 29)]; conf = [q for q in ks if q >= dt.date(2024, 1, 2)]
    print("%-30s DEV  %s" % (name, T.score(pd, dev))); print("%-30s CONF %s" % ("", T.score(pd, conf)), flush=True)
