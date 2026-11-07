"""Profit-taking variants for the NOISE bot on MNQ (QQQ 5-min proxy), scored on the 50K Combine.
Variants: per-trade take-profit with re-entry at the next hourly check, daily profit lock, trailing giveback."""
import csv, datetime as dt, gzip, statistics as st, sys
from collections import defaultdict
from zoneinfo import ZoneInfo
from noise import LAST, OPEN, decide, vol_scale
ET = ZoneInfo("America/New_York"); PER = 58000.0; COST = 0.00003  # $ per 1.0 unit return per contract; cost/side

def load(path):
    days = defaultdict(dict)
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            t = dt.datetime.fromisoformat(r["t"].replace("Z", "+00:00")).astimezone(ET)
            if OPEN <= t.time() <= LAST:
                days[t.date()][t.time()] = (float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))
    return {d: b for d, b in days.items() if OPEN in b and LAST in b and len(b) >= 70}

def day(history, today, n, tp=None, lock=None, trail=None):
    """Dollar path for n contracts. Returns dict c,x,w,end (cumulative $)."""
    S = n * PER; times = sorted(today); pos, entry, real = 0, None, 0.0; pend = None; stop_day = False; peak = 0.0
    c, x, w = [], [], []
    for i, t in enumerate(times):
        o, h, l, cl, v = today[t]
        if pend is not None and not stop_day:
            if pend != pos:
                if pos: real += S * (pos * (o / entry - 1) - COST); pos = 0
                if pend: pos, entry, peak = pend, o, 0.0; real -= S * COST
            pend = None
        if t == LAST:
            if pos: real += S * (pos * (o / entry - 1) - COST); pos = 0
            c.append(real); x.append(real); w.append(real); break
        op = lambda px: S * (pos * (px / entry - 1) - COST) if pos else 0.0
        w.append(real + op(l if pos > 0 else h))
        if pos and tp:                                   # resting limit at entry +/- tp dollars
            lvl = entry * (1 + pos * tp / S)
            pen = lvl * 0.00002 * pos   # require price to trade ~2 ticks through the limit
            if (pos > 0 and h >= lvl + pen) or (pos < 0 and l <= lvl + pen):
                real += S * (pos * (lvl / entry - 1) - COST); pos = 0
        c.append(real + op(cl))
        nxt = today[times[i + 1]][0] if i + 1 < len(times) else cl
        if stop_day:
            x.append(real); continue
        tg = decide(history, today, t, pos)
        if pos and trail:
            peak = max(peak, op(cl))
            if peak >= trail and op(cl) <= 0.5 * peak: tg = 0
        if lock and real + op(cl) >= lock:
            tg = 0; stop_day = True
        if tg is not None and tg != pos: pend = tg
        x.append(real + op(nxt))
    return {"c": c, "x": x, "w": w, "end": c[-1]}

def build(days, **kw):
    keys = sorted(days); out = {}
    for i, d in enumerate(keys):
        hist = [days[k] for k in keys[max(0, i - 20):i]]
        if len(hist) < 15: continue
        n = max(1, int(round(2 * vol_scale(hist))))
        out[d] = day(hist, days[d], n, **kw)
    return out

def day_pnl(p, room, lo, need_fn, buffer, dll):
    c, x, w = p["c"], p["x"], p["w"]
    for i in range(len(c)):
        if room + w[i] <= 0: return -room, True, False
        if w[i] <= -dll: return -dll, False, False
        if c[i] <= -lo: return x[i], False, False
        if room + c[i] <= buffer: return x[i], False, True
        if need_fn and need_fn(c[i]): return x[i], False, False
    return p["end"], False, False

def combine(seq, bal=0.0, hw=0.0, best=0.0, maxd=126):
    locked = False
    for i, p in enumerate(seq[:maxd], 1):
        floor = 0.0 if locked else min(0.0, hw - 2000); room = bal - floor
        need = lambda ci, bal=bal, best=best: bal + ci >= max(3000, max(best, ci) / 0.5)
        pnl, breach, near = day_pnl(p, room, 800, need, 400, 1000)
        bal += pnl
        if breach or near: return "fail", i
        best = max(best, pnl); hw = max(hw, bal); locked = locked or hw >= 2000
        if bal >= max(3000, best / 0.5): return "pass", i
    return "timeout", maxd

def score(pd, ks):
    seq = [pd[k] for k in ks]; ends = [p["end"] for p in seq]
    r = [combine(seq[s:]) for s in range(0, len(seq) - 130, 2)]
    now = [combine(seq[s:], -439.32, 66.84, 66.84) for s in range(0, len(seq) - 130, 2)]
    pr = sum(o == "pass" for o, _ in r) / len(r); pn = sum(o == "pass" for o, _ in now) / len(now)
    dd = [d for o, d in r if o == "pass"]
    return "$/day %5.0f  win %4.1f%%  pass(fresh) %4.1f%%  med days %3.0f  pass(from today) %4.1f%%" % (
        st.mean(ends), 100 * sum(e > 0 for e in ends) / len(ends), 100 * pr, st.median(dd) if dd else 0, 100 * pn)

if __name__ == "__main__":
    days = load(sys.argv[1])
    tests = [("current rules", {})] + [("take profit $%d + re-enter" % v, {"tp": v}) for v in (150, 250, 400, 600, 1000)] + \
            [("daily lock $%d" % v, {"lock": v}) for v in (300, 500, 800, 1200)] + \
            [("trail 50%% after $%d" % v, {"trail": v}) for v in (200, 400, 700)]
    for name, kw in tests:
        pd = build(days, **kw); ks = sorted(pd)
        dev = [k for k in ks if k <= dt.date(2023, 12, 29)]; conf = [k for k in ks if k >= dt.date(2024, 1, 2)]
        print("%-28s DEV  %s" % (name, score(pd, dev))); print("%-28s CONF %s" % ("", score(pd, conf)), flush=True)
