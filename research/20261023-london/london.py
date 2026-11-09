"""London-session tests on QQQ pre-market 5-min bars (4:00-9:25 ET), flat before the New York open.
L1 NOISE-London: same NOISE rules, session open 4:00, reference = prior 16:00 close, hourly checks 5:00..9:00.
L2 Range breakout: range of 4:00-4:55; enter on a 5-min close outside it (after 5:00), exit at 9:25 or opposite side.
L3 Pre-market drift: at 8:00 go with the sign of the move since the prior close; exit 9:25.
Costs per side as in the NY tests; unit = 1x notional."""
import csv, datetime as dt, gzip, statistics as st
from collections import defaultdict
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
COST = 0.00003
S0, S1 = dt.time(4, 0), dt.time(9, 25)

def load(path):
    pre, rth = defaultdict(dict), defaultdict(dict)
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            t = dt.datetime.fromisoformat(r["t"].replace("Z", "+00:00")).astimezone(ET)
            b = (float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))
            if S0 <= t.time() <= S1: pre[t.date()][t.time()] = b
            elif dt.time(9, 30) <= t.time() <= dt.time(15, 55): rth[t.date()][t.time()] = b
    return pre, rth

def trade(bars, signals):
    """signals: {time: target} decided at that bar's close; fill next bar open; flatten at 9:25 open."""
    times = sorted(bars); pos, ent, pnl, pend = 0, None, 0.0, None
    for i, t in enumerate(times):
        o = bars[t][0]
        if pend is not None and pend != pos:
            if pos: pnl += pos * (o / ent - 1) - COST; pos = 0
            if pend: pos, ent = pend, o; pnl -= COST
        pend = None
        if t >= S1:
            if pos: pnl += pos * (o / ent - 1) - COST; pos = 0
            break
        if t in signals: pend = signals[t]
    if pos: pnl += pos * (bars[times[-1]][3] / ent - 1) - COST
    return pnl

def run(pre, rth):
    days = sorted(d for d in pre if len(pre[d]) >= 50 and S1 in pre[d] and dt.time(4, 0) in pre[d])
    res = {"L1": {}, "L2": {}, "L3": {}}
    for i, d in enumerate(days):
        prevs = [x for x in sorted(rth) if x < d]
        if not prevs: continue
        pc = rth[prevs[-1]].get(dt.time(15, 55), (0, 0, 0, None))[3]
        if not pc: continue
        b = pre[d]; op = b[dt.time(4, 0)][0]
        # L1 NOISE-London
        hist = [pre[x] for x in days[max(0, i - 14):i]]
        sig = {}
        pos = 0; pv = vol = 0.0
        for t in sorted(b):
            o, h, l, c, v = b[t]; pv += (h + l + c) / 3 * v; vol += v; vw = pv / vol if vol else c
            if t.minute == 55 and dt.time(4, 55) <= t <= dt.time(8, 55):
                moves = [abs(x[t][3] / x[dt.time(4, 0)][0] - 1) for x in hist if t in x and dt.time(4, 0) in x]
                if len(moves) < 10: continue
                s = st.mean(moves); up, dn = max(op, pc) * (1 + s), min(op, pc) * (1 - s)
                tg = pos
                if pos > 0 and c < max(up, vw) or pos < 0 and c > min(dn, vw): tg = 0
                if tg == 0: tg = 1 if c > up else -1 if c < dn else 0
                if tg != pos: sig[t] = tg; pos = tg
        res["L1"][d] = trade(b, sig)
        # L2 range breakout
        rng = [b[t] for t in b if t < dt.time(5, 0)]
        hi, lo = max(x[1] for x in rng), min(x[2] for x in rng)
        sig, pos = {}, 0
        for t in sorted(b):
            if t < dt.time(5, 0) or t >= S1: continue
            c = b[t][3]
            tg = 1 if c > hi else -1 if c < lo else pos
            if tg != pos: sig[t] = tg; pos = tg
        res["L2"][d] = trade(b, sig)
        # L3 pre-market drift from 8:00
        t8 = dt.time(7, 55)
        if t8 in b:
            res["L3"][d] = trade(b, {t8: 1 if b[t8][3] > pc else -1})
    return res

def stats(vals):
    if not vals: return "n/a"
    m = st.mean(vals); sd = st.pstdev(vals) or 1e-9
    return "mean %5.2fbp  win %4.1f%%  sharpe %5.2f  traded %4.1f%%  n=%d" % (
        m * 1e4, 100 * sum(v > 0 for v in vals) / max(1, sum(v != 0 for v in vals)), m / sd * 252 ** 0.5,
        100 * sum(v != 0 for v in vals) / len(vals), len(vals))

if __name__ == "__main__":
    import pickle
    pre, rth = load('/home/claude/data/qqq/QQQ_5m.csv.gz')
    res = run(pre, rth)
    pickle.dump(res, open('/home/claude/data/qqq/london.pkl', 'wb'))
    split = dt.date(2024, 1, 1)
    for k, r in res.items():
        dev = [v for d, v in r.items() if d < split]; conf = [v for d, v in r.items() if d >= split]
        print("%s DEV  %s" % (k, stats(dev))); print("%s CONF %s" % (k, stats(conf)))
