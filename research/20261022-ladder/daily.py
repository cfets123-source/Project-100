"""Per-day NOISE paths for the ladder simulation, using the bot's own decision code (prop/noise.py).

For every regular-session day we record, per 5-minute bar i (one unit = long/short 1x the futures price):
  c[i]  cumulative P&L fraction marked at bar i's close (incl. the exit cost if flattened there)
  x[i]  cumulative P&L fraction if the bot flattens at the next bar's open (what happens after a stop/target check)
  w[i]  worst cumulative P&L fraction inside bar i (high/low) - used for the firm's intraday loss-limit breach
  end   final P&L fraction after the 15:55 flatten
Fills: decisions after bar t closes fill at bar t+1's open (the bot acts within seconds of the close).
Costs: COST per side as a fraction of notional.
"""
import csv
import datetime as dt
import gzip
import os
import pickle
import sys
from collections import defaultdict
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "prop"))
from noise import LAST, OPEN, decide  # noqa: E402

ET = ZoneInfo("America/New_York")
COST = 0.00003  # per side: ~$0.37 commission + 1 tick slippage on a ~$58k MNQ contract, doubled for safety


def load(path):
    days = defaultdict(dict)
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            t = dt.datetime.fromisoformat(r["t"].replace("Z", "+00:00")).astimezone(ET)
            if OPEN <= t.time() <= LAST:
                days[t.date()][t.time()] = (float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))
    return {d: b for d, b in days.items() if OPEN in b and LAST in b and len(b) >= 70}


def day_path(history, today, cost=COST):
    times = sorted(today)
    pos, entry, real = 0, None, 0.0
    c, x, w = [], [], []
    pending = None  # target to execute at the next bar's open
    for i, t in enumerate(times):
        o, h, l, cl, v = today[t]
        if pending is not None and t != times[0]:
            if pending != pos:
                if pos:
                    real += pos * (o / entry - 1) - cost
                    pos = 0
                if pending:
                    pos, entry = pending, o
                    real -= cost
            pending = None
        if t == LAST:  # the bot flattens at 15:55 (open of the last bar)
            if pos:
                real += pos * (o / entry - 1) - cost
                pos = 0
            c.append(real); x.append(real); w.append(real)
            break
        openpnl = lambda px: (pos * (px / entry - 1) - cost) if pos else 0.0  # noqa: E731
        worst_px = l if pos > 0 else h
        w.append(real + (openpnl(worst_px) if pos else 0.0))
        c.append(real + openpnl(cl))
        nxt = today[times[i + 1]][0] if i + 1 < len(times) else cl
        target = decide(history, today, t, pos)
        if target is not None and target != pos:
            pending = target
        x.append(real + openpnl(nxt))
    return {"c": c, "x": x, "w": w, "end": c[-1]}


def build(path, out):
    days = load(path)
    keys = sorted(days)
    res = {}
    for i, d in enumerate(keys):
        hist = [days[k] for k in keys[max(0, i - 20):i]]
        if len(hist) < 10:
            continue
        res[d] = day_path(hist, days[d])
    with open(out, "wb") as fh:
        pickle.dump(res, fh)
    return res


if __name__ == "__main__":
    r = build(sys.argv[1], sys.argv[2])
    ends = [v["end"] for v in r.values()]
    print(len(r), min(r), max(r), "mean/day %.6f" % (sum(ends) / len(ends)),
          "win%% %.1f" % (100 * sum(e > 0 for e in ends) / len(ends)),
          "trade days %.1f%%" % (100 * sum(e != 0 for e in ends) / len(ends)))
