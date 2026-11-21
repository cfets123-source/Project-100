"""Read-only: show what the bot saw at every hourly check for the last few days (no orders)."""
import datetime as dt, sys, os
sys.path.insert(0, os.path.expanduser("~/p100-prop"))
import worker
from noise import LAST, OPEN, decide, is_check, sigma, vwap, vol_scale
from topstepx import TopstepX
api = TopstepX(*worker.credentials()); c = api.contract("MNQ")
now = dt.datetime.now(worker.ET)
raw = api.bars(c["id"], worker.iso(now - dt.timedelta(days=45)), worker.iso(now))
days = worker.group_days(raw); keys = sorted(d for d in days if OPEN in days[d])
for d in keys[-5:]:
    hist = [days[k] for k in keys if k < d and LAST in days[k]][-20:]
    today = days[d]; pc = hist[-1][LAST][3]; op = today[OPEN][0]
    print("\n%s  history %d days, prev close %.2f, open %.2f, size scale %.2f" % (d, len(hist), pc, op, vol_scale(hist)))
    pos = 0
    for t in sorted(today):
        if not is_check(t): continue
        s = sigma(hist, t)
        up, dn = max(op, pc) * (1 + s), min(op, pc) * (1 - s)
        tg = decide(hist, today, t, pos)
        print("  %s close %.2f  buy above %.2f  sell below %.2f  vwap %.2f  -> %s" % (
            (dt.datetime.combine(d, t) + dt.timedelta(minutes=5)).strftime("%H:%M"), today[t][3], up, dn, vwap(today, t),
            {1: "LONG", -1: "SHORT", 0: "flat"}[tg]))
        pos = tg
