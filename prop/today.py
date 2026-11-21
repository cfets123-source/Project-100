"""Read-only: today's 5-min MNQ bars from 12:55 to the close, with the bot's take-profit level for its short."""
import datetime as dt, os, sys
sys.path.insert(0, os.path.expanduser("~/p100-prop"))
import worker
from topstepx import TopstepX
api = TopstepX(*worker.credentials()); c = api.contract("MNQ")
d = dt.date(2026, 10, 30)
s = dt.datetime.combine(d, dt.time(12, 55), worker.ET); e = dt.datetime.combine(d, dt.time(16, 0), worker.ET)
bars = sorted(api.bars(c["id"], worker.iso(s), worker.iso(e)), key=lambda b: b["t"])
for b in bars:
    print(worker.to_et(b["t"]).strftime("%H:%M"), "open %.2f high %.2f low %.2f close %.2f" % (b["o"], b["h"], b["l"], b["c"]))
for a in api.accounts():
    if "50KTC" in a.get("name", ""):
        for t in api.trades(a["id"], worker.iso(dt.datetime.combine(d, dt.time(9, 0), worker.ET))):
            print("FILL", t.get("creationTimestamp", "")[11:19], "side", t.get("side"), "size", t.get("size"), "price", t.get("price"), "pnl", t.get("profitAndLoss"))
