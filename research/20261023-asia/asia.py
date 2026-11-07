"""Asia-session first look on MNQ futures (TopstepX history, ~2 months). Session 18:00-02:55 ET, flat by 03:00.
A1 Momentum: at 20:00 go with the move since the 18:00 open, exit 02:55.
A2 Continuation: at 18:05 go with the direction of the prior NY session (9:30 open -> 15:55 close), exit 02:55.
A3 Range breakout: range of 18:00-18:55, enter on a 5-min close outside it, exit 02:55 or opposite side."""
import csv, datetime as dt, gzip, statistics as st
from collections import defaultdict
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York"); COST = 0.00003
def load(path):
    bars = {}
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            t = dt.datetime.fromisoformat(r["t"].replace("Z", "+00:00")).astimezone(ET)
            bars[t] = (float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]))
    return bars
def sessions(bars):
    """{session_date (the evening it starts): {datetime: bar}} for 18:00 -> 02:55 next morning."""
    out = defaultdict(dict)
    for t, b in bars.items():
        if t.time() >= dt.time(18, 0): out[t.date()][t] = b
        elif t.time() <= dt.time(2, 55): out[t.date() - dt.timedelta(days=1)][t] = b
    return out
def run():
    bars = load('/home/claude/data/mnq_5m.csv.gz'); S = sessions(bars)
    rth = defaultdict(dict)
    for t, b in bars.items():
        if dt.time(9, 30) <= t.time() <= dt.time(15, 55): rth[t.date()][t.time()] = b
    res = {"A1": [], "A2": [], "A3": []}
    for d in sorted(S):
        s = S[d]; ts = sorted(s)
        if len(ts) < 90 or d.weekday() == 4: continue        # skip Friday evenings (market closed)
        first, last = s[ts[0]], s[ts[-1]]
        op, cl = first[0], last[3]
        def at(hh, mm):
            k = [t for t in ts if t.time() == dt.time(hh, mm)]
            return s[k[0]][3] if k else None
        p20 = at(19, 55)
        if p20: res["A1"].append((1 if p20 > op else -1) * (cl / p20 - 1) - 2 * COST)
        if d in rth and dt.time(9, 30) in rth[d] and dt.time(15, 55) in rth[d]:
            dirn = 1 if rth[d][dt.time(15, 55)][3] > rth[d][dt.time(9, 30)][0] else -1
            res["A2"].append(dirn * (cl / op - 1) - 2 * COST)
        hi = max(s[t][1] for t in ts if t.time() >= dt.time(18, 0) and t.time() < dt.time(19, 0))
        lo = min(s[t][2] for t in ts if t.time() >= dt.time(18, 0) and t.time() < dt.time(19, 0))
        pos, ent, pnl = 0, None, 0.0
        for t in ts:
            if dt.time(18, 0) <= t.time() < dt.time(19, 0): continue
            c = s[t][3]; tg = 1 if c > hi else -1 if c < lo else pos
            if tg != pos:
                if pos: pnl += pos * (c / ent - 1) - COST
                pos, ent = tg, c; pnl -= COST
        if pos: pnl += pos * (cl / ent - 1) - COST
        res["A3"].append(pnl)
    for k, v in res.items():
        m = st.mean(v); sd = st.pstdev(v) or 1e-9
        print("%s nights %2d  mean %+6.2fbp  win %4.1f%%  sharpe %+5.2f  total at 2 MNQ $%+.0f" % (
            k, len(v), m * 1e4, 100 * sum(x > 0 for x in v) / len(v), m / sd * 252 ** 0.5, sum(v) * 2 * 58000))
run()
