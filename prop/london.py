"""London pre-market drift, DRY RUN only (research/20261023-london, strategy L3).

At 8:00 ET (after the 7:55 bar closes) take the side of the move since the prior regular-session close; exit at 9:25.
Never places orders: it records what it would have done, reports it as events on the app, and keeps a running log in
~/.p100-prop/london.json so live results can be compared with the simulation after a few weeks.
"""
import datetime as dt
import json
import logging
import os

log = logging.getLogger("prop")
ENTRY_BAR, EXIT_BAR = dt.time(7, 55), dt.time(9, 20)   # decide on the 7:55 bar's close, exit on the 9:20 bar's close
CONTRACTS = 2
COMMISSION_PER_SIDE = 0.37


class LondonDrift:
    def __init__(self, api, cid, point_value, event_fn, home, to_et, iso, group_days, et):
        self.api, self.cid, self.pv, self.event = api, cid, point_value, event_fn
        self.to_et, self.iso, self.group_days, self.ET = to_et, iso, group_days, et
        self.path = os.path.join(home, "london.json")
        self.log = []
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.log = json.load(f)
        self.day, self.side, self.entry, self.done = None, 0, None, False

    def _bar_close(self, day, start_t):
        start = dt.datetime.combine(day, start_t, self.ET)
        for b in self.api.bars(self.cid, self.iso(start), self.iso(start + dt.timedelta(minutes=5))):
            if self.to_et(b["t"]).time() == start_t:
                return float(b["c"])
        return None

    def _prev_close(self, day):
        start = dt.datetime.combine(day - dt.timedelta(days=5), dt.time(0), self.ET)
        end = dt.datetime.combine(day, dt.time(0), self.ET)
        days = self.group_days(self.api.bars(self.cid, self.iso(start), self.iso(end)))
        for d in sorted(days, reverse=True):
            if dt.time(15, 55) in days[d]:
                return days[d][dt.time(15, 55)][3]
        return None

    def step(self, now):
        if now.weekday() >= 5:
            return
        day = now.date()
        if self.day != day:
            self.day, self.side, self.entry, self.done = day, 0, None, any(r["date"] == day.isoformat() for r in self.log)
        if self.done:
            return
        t = now.time()
        if not self.side and dt.time(8, 0) <= t < dt.time(8, 15):
            px, pc = self._bar_close(day, ENTRY_BAR), self._prev_close(day)
            if px is None or pc is None:
                return
            self.side, self.entry = (1 if px > pc else -1), px
            self.event("london", "[London dry run] %s %d MNQ at %.2f (pre-market %s %.2f%% since yesterday's close)" % (
                "Bought" if self.side > 0 else "Sold short", CONTRACTS, px, "up" if px > pc else "down",
                abs(px / pc - 1) * 100), px, CONTRACTS)
        elif self.side and t >= dt.time(9, 25):
            px = self._bar_close(day, EXIT_BAR)
            if px is None:
                return
            pnl = (px - self.entry) * self.side * CONTRACTS * self.pv - 2 * COMMISSION_PER_SIDE * CONTRACTS
            self.log.append({"date": day.isoformat(), "side": self.side, "entry": self.entry, "exit": px,
                             "pnl": round(pnl, 2)})
            with open(self.path, "w") as f:
                json.dump(self.log, f, indent=1)
            total = sum(r["pnl"] for r in self.log)
            self.event("london", "[London dry run] Closed at %.2f: %+.2f today, %+.2f over %d days" % (
                px, pnl, total, len(self.log)), px, CONTRACTS, pnl)
            self.done, self.side = True, 0
        elif not self.side and t >= dt.time(8, 15):
            self.done = True   # started too late to take today's entry

    def summary(self):
        n = len(self.log)
        return {"days": n, "total": round(sum(r["pnl"] for r in self.log), 2),
                "wins": sum(1 for r in self.log if r["pnl"] > 0)}
