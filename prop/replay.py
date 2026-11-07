"""Read-only daily check: replay the bot's rules on today's real MNQ bars and compare with the account's real fills.
Usage: python3 ~/Documents/p100-prop/replay.py [YYYY-MM-DD]"""
import datetime as dt, math, os, sys
sys.path.insert(0, os.path.expanduser("~/p100-prop"))
import worker
from noise import LAST, OPEN, decide, vol_scale
from topstepx import TopstepX
day = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.datetime.now(worker.ET).date()
api = TopstepX(*worker.credentials()); c = api.contract("MNQ")
end = dt.datetime.combine(day, dt.time(16, 5), worker.ET)
days = worker.group_days(api.bars(c["id"], worker.iso(end - dt.timedelta(days=40)), worker.iso(end)))
hist = [days[d] for d in sorted(days) if d < day and OPEN in days[d] and LAST in days[d]][-20:]
today = days.get(day, {})
if not today:
    sys.exit("no bars for %s" % day)
n = max(1, int(round(round(100000 / (today[OPEN][0] * 2)) * vol_scale(hist))))
TP, PV, FEE = 600.0, 2.0, 0.74            # $ take-profit (2 contracts / 50K Combine), $/point, round-trip fee/contract
pos, avg, pnl, pend, log = 0, None, 0.0, None, []
times = sorted(today)
for i, t in enumerate(times):
    o, h, l, cl, v = today[t]
    if pend is not None and pend != pos:
        if pos:
            pnl += (o - avg) * pos * PV - FEE * abs(pos); log.append("%s exit %+d at %.2f" % (t, pos, o)); pos = 0
        if pend:
            pos, avg = pend * n, o; log.append("%s enter %+d at %.2f" % (t, pos, o))
    pend = None
    if t == LAST:
        if pos:
            pnl += (o - avg) * pos * PV - FEE * abs(pos); log.append("%s end-of-day exit %+d at %.2f" % (t, pos, o)); pos = 0
        break
    if pos:
        move = TP / (abs(pos) * PV)
        lvl = (math.ceil((avg + move) / .25) if pos > 0 else math.floor((avg - move) / .25)) * .25
        if (pos > 0 and h >= lvl) or (pos < 0 and l <= lvl):
            pnl += (lvl - avg) * pos * PV - FEE * abs(pos); log.append("%s take-profit %+d at %.2f" % (t, pos, lvl)); pos = 0
    tg = decide(hist, today, t, (pos > 0) - (pos < 0))
    if tg is not None and tg != (pos > 0) - (pos < 0):
        pend = tg
print("REPLAY %s (%d contracts):" % (day, n)); print("  " + "\n  ".join(log or ["no trades"]))
print("  replay P&L  %+.2f" % pnl)
real = 0.0
for a in api.accounts():
    if "50KTC" in (a.get("name") or ""):
        s = dt.datetime.combine(day, dt.time(0), worker.ET)
        for f in api.trades(a["id"], worker.iso(s), worker.iso(end)):
            real += float(f.get("profitAndLoss") or 0) - float(f.get("fees") or 0)
            print("  FILL %s side %s size %s price %s pnl %s" % (str(f.get("creationTimestamp"))[11:19], f.get("side"), f.get("size"), f.get("price"), f.get("profitAndLoss")))
print("  actual P&L  %+.2f   difference %+.2f %s" % (real, real - pnl, "OK" if abs(real - pnl) < 60 else "<-- CHECK"))
