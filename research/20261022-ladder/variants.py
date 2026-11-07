"""NOISE variants for prop-firm use. Tuned on 2019-2023 (dev), confirmed on 2024-2026 (conf).
Each variant changes one thing vs the bot's current rules; scored by expected profit per 50K Combine attempt."""
import datetime as dt, pickle, statistics as st, sys
sys.path.insert(0, '.')
import daily, ladder as L, econ, econ2
from noise import LAST, OPEN, is_check, sigma, vwap

def decide_v(history, today, t, position, k=1.0, every=30, stop=None, entry=None):
    if not is_check(t) or (every == 60 and t.minute != 55): return None
    prev_close = history[-1].get(LAST, (None,) * 4)[3]
    s = sigma(history, t)
    if prev_close is None or s is None: return None
    op, c = today[OPEN][0], today[t][3]
    up, dn = max(op, prev_close) * (1 + k * s), min(op, prev_close) * (1 - k * s)
    vw = vwap(today, t); target = position
    if position > 0 and c < max(up, vw): target = 0
    elif position < 0 and c > min(dn, vw): target = 0
    if stop and position and entry and position * (c / entry - 1) < -stop * s: target = 0
    if target == 0: target = 1 if c > up else -1 if c < dn else 0
    return target

def day_path(history, today, scale=1.0, cost=daily.COST, **kw):
    times = sorted(today); pos, entry, real = 0, None, 0.0; c, x, w = [], [], []; pending = None
    for i, t in enumerate(times):
        o, h, l, cl, v = today[t]
        if pending is not None:
            if pending != pos:
                if pos: real += pos * (o / entry - 1) - cost; pos = 0
                if pending: pos, entry = pending, o; real -= cost
            pending = None
        if t == LAST:
            if pos: real += pos * (o / entry - 1) - cost; pos = 0
            c.append(real); x.append(real); w.append(real); break
        op_ = lambda px: (pos * (px / entry - 1) - cost) if pos else 0.0
        w.append(real + op_(l if pos > 0 else h)); c.append(real + op_(cl))
        nxt = today[times[i + 1]][0] if i + 1 < len(times) else cl
        tg = decide_v(history, today, t, pos, entry=entry, **kw)
        if tg is not None and tg != pos: pending = tg
        x.append(real + op_(nxt))
    return {"c": c, "x": x, "w": w, "end": c[-1], "scale": scale}

def build(days, voltarget=None, **kw):
    keys = sorted(days); res = {}
    for i, d in enumerate(keys):
        hist = [days[k] for k in keys[max(0, i - 20):i]]
        if len(hist) < 10: continue
        scale = 1.0
        if voltarget:
            rets = [hist[j][LAST][3] / hist[j - 1][LAST][3] - 1 for j in range(1, len(hist))][-14:]
            vol = st.pstdev(rets) or 1e-9
            scale = max(0.5, min(2.0, voltarget / vol))
        res[d] = day_path(hist, days[d], scale, **kw)
    return L.prep(res)

def score(pdays, keys, label):
    seq = [pdays[k] for k in keys]; T = L.TYPES[50]
    starts = range(0, len(seq) - 130, 2); xs = range(0, len(seq) - 260, 2)
    r = [econ.combine(seq[s:], 2, T) for s in starts]
    rate = sum(o == "pass" for o, _ in r) / len(r)
    fees = st.mean(49 * (1 + (d - 1) // 21) for o, d in r)
    v = [econ2.xfa(seq[s:], T, 2500, 2, 150, 3000, "standard", maxd=252)[0] for s in xs]
    xv = st.mean(v)
    ev = rate * (xv - 149) - fees
    mean = st.mean(p["end"] for p in seq) * 1e4
    return "%-26s %-5s day %5.2fbp pass %4.1f%% fees %3.0f xfa1y $%5.0f  EV/attempt $%6.0f" % (label, "", mean, 100 * rate, fees, xv, ev), ev

if __name__ == "__main__":
    raw = daily.load('/home/claude/data/qqq/QQQ_5m.csv.gz')
    dev = lambda ks: [k for k in ks if k <= dt.date(2023, 12, 29)]
    conf = lambda ks: [k for k in ks if k >= dt.date(2024, 1, 2)]
    tests = [("base", {}), ("k=0.8", {"k": 0.8}), ("k=1.2", {"k": 1.2}), ("k=1.5", {"k": 1.5}),
             ("hourly checks", {"every": 60}), ("stop 1 sigma", {"stop": 1.0}), ("stop 2 sigma", {"stop": 2.0}),
             ("vol target 1.0%", {"voltarget": 0.010}), ("vol target 1.3%", {"voltarget": 0.013})]
    for name, kw in tests:
        pd = build(raw, **kw); ks = sorted(pd)
        a, ea = score(pd, dev(ks), name + " DEV"); b, eb = score(pd, conf(ks), name + " CONF")
        print(a); print(b, flush=True)
