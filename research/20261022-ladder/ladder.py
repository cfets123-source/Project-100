"""Full prop-firm ladder simulation: Combines -> funded accounts (XFA) -> payouts -> reinvestment.

Every account trades the same NOISE signal on the same day (as the real bot does with ACCOUNT=ALL), so accounts
win and lose together. Rules follow Topstep as published (Oct 2026); the bot's own guards are applied on top.
Input: per-day paths from daily.py (unit = 1x the futures price, long or short).
"""
import math
import pickle
import random
import statistics as st
from dataclasses import dataclass, field

import numpy as np

PX = 29000.0            # MNQ index level used to convert unit returns to dollars (Oct 2026)
PER_CONTRACT = PX * 2   # $ per 1.0 unit return per MNQ contract
API_FEE, API_EVERY = 14.50, 21
SPLIT = 0.90
PAYOUT_LAG = 3          # trading days from request to cash
CONSISTENCY = 0.50

# size: contracts the bot trades, MLL, target, bot daily stop, bot MLL buffer, firm daily loss limit,
#       monthly fee (Standard path), activation, payout cap (Standard path)
TYPES = {
    50: dict(n=2, mll=2000, target=3000, stop=800, buffer=400, dll=1000, fee=49, act=149, cap=2000),
    100: dict(n=3, mll=3000, target=6000, stop=1600, buffer=600, dll=2000, fee=99, act=149, cap=3000),
    150: dict(n=6, mll=4500, target=9000, stop=2400, buffer=900, dll=3000, fee=149, act=149, cap=5000),
}


@dataclass
class Policy:
    start_cash: float = 0.0          # owner cash on day 0 (beyond the Combine already paid)
    budget: float = 500.0            # most the owner will ever put in (fees/activations not covered by payouts)
    stagger_days: int = 0            # wait at least this many trading days between Combine purchases
    max_xfa: int = 5
    extra_combines: int = 1          # Combines allowed in addition to funded accounts
    max_combines: int = 6            # Combines running at the same time (they all trade the same signal)
    reserve_months: float = 2.0      # cash kept back for fees before buying another Combine
    upgrade_cash: float = 2500.0     # buy 150K Combines once spare cash exceeds this
    buffer_mode: str = "finish"      # bot behaviour near the loss limit: "finish" (abandon) or "pause" (stop the day)
    payout_frac: float = 0.50        # fraction of balance requested (firm caps at 50% and the size cap)
    min_cushion: float = 0.0         # do not request a payout that leaves less than this balance
    xfa_policy: str = "v2"           # "v1" = original bot (fixed contracts, $400 buffer, 50% payouts); "v2" = cushion-based
    xfa_per: float = 2500.0          # v2: $ of room per contract
    xfa_nmax_per50: int = 2          # v2: max contracts per $50K of account size
    cushion_per50: float = 3000.0    # v2: balance kept after each payout per $50K of size
    xfa_buffer: float = 150.0        # v2: bot stops for good this close to the loss limit
    broker_rate: float = 0.0         # Stage 5: annual return on cash moved to the owner's brokerage account
    working_cash: float = 3000.0     # cash kept for prop fees; anything above is moved to the brokerage


@dataclass
class Acct:
    kind: str                  # "combine" or "xfa"
    size: int
    bal: float = 0.0
    hw: float = 0.0
    best: float = 0.0
    locked: bool = False
    wins: int = 0
    paid_any: bool = False
    age: int = 0
    dead: bool = False
    passed: bool = False


def day_pnl(path, n, room, lo, need_fn, buffer, dll, bal):
    """Dollar P&L for one account on one day. Returns (pnl, breached, finished_near_floor)."""
    n = max(1, int(round(n * path.get("scale", 1.0))))   # volatility sizing in whole contracts
    s = n * PER_CONTRACT
    end = path["end"]
    if end == 0.0 and path["flat"]:
        return 0.0, False, False
    c, x, w = path["c"], path["x"], path["w"]
    for i in range(len(c)):
        wi = w[i] * s
        if room + wi <= 0:
            return -room, True, False
        if wi <= -dll:
            return -dll, False, False
        ci = c[i] * s
        if ci <= -lo:
            return x[i] * s, False, False
        if room + ci <= buffer:
            return x[i] * s, False, True
        if need_fn is not None and need_fn(ci):
            return x[i] * s, False, False
    return end * s, False, False


class Ladder:
    def __init__(self, pol, rng=None):
        self.p = pol
        self.cash = pol.start_cash
        self.accts = [Acct("combine", 50)]
        self.fee_due = {id(self.accts[0]): 0}
        self.pending = []      # (day_due, amount)
        self.t = 0
        self.fees = 49.0       # first month already paid (counted as cost)
        self.payouts = 0.0
        self.owner_in = pol.start_cash   # wealth is measured net of the owner's own money
        self.broke = False
        self.broker = 0.0
        self.last_buy = 0
        self.log = {"combines": 1, "passes": 0, "fails_combine": 0, "fails_xfa": 0, "first_payout": None,
                    "payout_n": 0, "stuck_activation_days": 0}
        self.owner_act_used = False
        self.waiting = []      # passed Combines waiting for activation money

    # ---- money --------------------------------------------------------------------------------------------
    def monthly_burn(self):
        return API_FEE + sum(TYPES[a.size]["fee"] for a in self.accts if a.kind == "combine" and not a.dead)

    def pay(self, amt):
        """Pay from cash; any shortfall comes from the owner's pocket, up to the budget."""
        short = amt - max(self.cash, 0.0)
        if short > 0:
            if self.owner_in + short > self.p.budget + self.p.start_cash:
                self.broke = True
                return False
            self.owner_in += short
            self.cash += short
        self.cash -= amt
        self.fees += amt
        return True

    def can_afford(self, amt):
        return max(self.cash, 0.0) + (self.p.budget + self.p.start_cash - self.owner_in) >= amt

    # ---- one trading day ----------------------------------------------------------------------------------
    def step(self, path):
        p = self.p
        self.t += 1
        if self.t % API_EVERY == 0:
            self.pay(API_FEE)
        for due, amt in [x for x in self.pending if x[0] <= self.t]:
            self.cash += amt
            self.pending.remove((due, amt))
        for a in self.accts:
            if a.dead:
                continue
            T = TYPES[a.size]
            a.age += 1
            if a.kind == "combine" and a.age % 21 == 0:
                self.pay(T["fee"])
            floor = 0.0 if (a.locked or (a.kind == "xfa" and a.paid_any)) else min(0.0, a.hw - T["mll"])
            room = a.bal - floor
            need_fn = None
            if a.kind == "combine":
                tgt, best, bal = T["target"], a.best, a.bal

                def need_fn(ci, tgt=tgt, best=best, bal=bal):
                    need = max(tgt, max(best, ci) / CONSISTENCY)
                    return bal + ci >= need
            n, stop, buf = T["n"], T["stop"], T["buffer"]
            if a.kind == "xfa" and p.xfa_policy == "v2":
                k = a.size // 50
                n = max(1, min(p.xfa_nmax_per50 * k, int(room // p.xfa_per)))
                stop, buf = 400 * n, p.xfa_buffer * k
            pnl, breach, near = day_pnl(path, n, room, stop, need_fn, buf, T["dll"], a.bal)
            a.bal += pnl
            if breach or (near and p.buffer_mode == "finish"):
                a.dead = True
                self.log["fails_combine" if a.kind == "combine" else "fails_xfa"] += 1
                continue
            a.best = max(a.best, pnl)
            a.hw = max(a.hw, a.bal)
            if a.hw - T["mll"] >= 0:
                a.locked = True
            if a.kind == "combine":
                need = max(T["target"], a.best / CONSISTENCY)
                if a.bal >= need:
                    a.dead, a.passed = True, True
                    self.log["passes"] += 1
                    self.waiting.append(a.size)
            else:
                if pnl >= 150:
                    a.wins += 1
                if a.wins >= 5:
                    amt = min(p.payout_frac * a.bal, 0.5 * a.bal, T["cap"])
                    if p.xfa_policy == "v2":
                        amt = min(amt, a.bal - p.cushion_per50 * (a.size // 50))
                    if amt >= 125 and a.bal - amt >= p.min_cushion:
                        a.bal -= amt
                        a.wins, a.paid_any = 0, True
                        a.hw = a.bal
                        self.pending.append((self.t + PAYOUT_LAG, amt * SPLIT))
                        self.payouts += amt * SPLIT
                        self.log["payout_n"] += 1
                        if self.log["first_payout"] is None:
                            self.log["first_payout"] = self.t
        self.activate()
        self.buy()
        if p.broker_rate and self.cash > p.working_cash:
            self.broker += self.cash - p.working_cash
            self.cash = p.working_cash
        self.broker *= 1 + p.broker_rate / 252

    def live_xfa(self):
        return sum(1 for a in self.accts if a.kind == "xfa" and not a.dead)

    def live_combines(self):
        return sum(1 for a in self.accts if a.kind == "combine" and not a.dead)

    def activate(self):
        while self.waiting and self.live_xfa() < self.p.max_xfa:
            size = self.waiting[0]
            cost = TYPES[size]["act"]
            if self.can_afford(cost):
                self.pay(cost)
            else:
                self.log["stuck_activation_days"] += 1
                return
            self.waiting.pop(0)
            self.accts.append(Acct("xfa", size))
        if self.waiting and self.live_xfa() >= self.p.max_xfa:
            self.waiting.clear()   # cannot hold more funded accounts; the pass is wasted

    def buy(self):
        p = self.p
        while (self.live_xfa() + self.live_combines() + len(self.waiting) < p.max_xfa + p.extra_combines
               and self.live_combines() < p.max_combines):
            nothing_alive = not any(not a.dead for a in self.accts) and not self.waiting
            spare = self.cash - p.reserve_months * self.monthly_burn()
            size = 150 if spare >= p.upgrade_cash else 50
            cost = TYPES[size]["fee"] + TYPES[size]["act"]   # first month + money for its activation later
            if nothing_alive:   # restart: owner money may be used, keeping $149 for the activation
                if not self.can_afford(TYPES[50]["fee"] + TYPES[50]["act"]):
                    return
                size, spare, cost = 50, float("inf"), 0
            if spare < cost or self.t - self.last_buy < p.stagger_days and not nothing_alive:
                return
            self.last_buy = self.t
            self.pay(TYPES[size]["fee"])
            self.accts.append(Acct("combine", size))
            self.log["combines"] += 1

    def wealth(self):
        """Owner's net result: cash on hand + payouts in transit - money the owner put in."""
        return self.cash + self.broker + sum(a for _, a in self.pending) - self.owner_in

    def ruined(self):
        return self.broke or (not any(not a.dead for a in self.accts) and not self.pending
                              and not self.can_afford(TYPES[50]["fee"] + (0 if self.waiting else TYPES[50]["act"])))


def run_path(paths, pol, milestones=(1000, 10000, 50000, 100000, 1000000)):
    L = Ladder(pol)
    hit = {m: None for m in milestones}
    ruin_day = None
    curve = []
    for d, path in enumerate(paths, 1):
        L.step(path)
        w = L.wealth()
        curve.append(w)
        for m in milestones:
            if hit[m] is None and w >= m:
                hit[m] = d
        if L.ruined():
            ruin_day = d
            break
    return {"hit": hit, "ruin": ruin_day, "end": L.wealth(), "log": L.log, "fees": L.fees, "max_in": L.owner_in,
            "payouts": L.payouts, "owner_in": L.owner_in, "curve": curve}


# ---- path generators --------------------------------------------------------------------------------------
def prep(days):
    out = {}
    for d, v in days.items():
        out[d] = {"c": np.asarray(v["c"]), "x": np.asarray(v["x"]), "w": np.asarray(v["w"]), "end": v["end"],
                  "flat": all(abs(e) < 1e-12 for e in v["c"]), "scale": v.get("scale", 1.0)}
        out[d]["c"], out[d]["x"], out[d]["w"] = out[d]["c"].tolist(), out[d]["x"].tolist(), out[d]["w"].tolist()
    return out


def haircut(days, frac):
    """Remove `frac` of the average daily edge, charged on days with trades (models a weaker future edge)."""
    if frac <= 0:
        return days
    traded = [v for v in days.values() if not v["flat"]]
    mean = sum(v["end"] for v in days.values()) / len(days)
    h = frac * mean * len(days) / len(traded)
    out = {}
    for d, v in days.items():
        if v["flat"]:
            out[d] = v
        else:
            out[d] = {"c": [x - h for x in v["c"]], "x": [x - h for x in v["x"]], "w": [x - h for x in v["w"]],
                      "end": v["end"] - h, "flat": False, "scale": v.get("scale", 1.0)}
    return out


def bootstrap(keys, days, n_days, rng, block=20):
    out = []
    while len(out) < n_days:
        s = rng.randrange(0, len(keys) - block)
        out.extend(days[k] for k in keys[s:s + block])
    return out[:n_days]


def summarize(results, horizon, milestones=(1000, 10000, 50000, 100000, 1000000)):
    n = len(results)
    rows = []
    for m in milestones:
        hits = [r["hit"][m] for r in results if r["hit"][m] is not None]
        rows.append((m, len(hits) / n, (st.median(hits) / 21) if hits else None))
    ruin = sum(1 for r in results if r["ruin"] is not None) / n
    first_pay = [r["log"]["first_payout"] for r in results if r["log"]["first_payout"]]
    ends = sorted(r["end"] for r in results)
    q = lambda f: ends[min(len(ends) - 1, int(f * len(ends)))]  # noqa: E731
    return {"n": n, "milestones": rows, "ruin": ruin,
            "first_payout_p": len(first_pay) / n,
            "first_payout_months": st.median(first_pay) / 21 if first_pay else None,
            "end_p10": q(0.10), "end_p50": q(0.50), "end_p90": q(0.90),
            "passes": st.mean(r["log"]["passes"] for r in results),
            "combines": st.mean(r["log"]["combines"] for r in results),
            "xfa_fails": st.mean(r["log"]["fails_xfa"] for r in results),
            "payouts": st.mean(r["log"]["payout_n"] for r in results),
            "owner_in": st.mean(r["owner_in"] for r in results),
            "owner_in_p90": sorted(r["max_in"] for r in results)[int(0.9 * n) - 1],
            "horizon_months": horizon / 21}


def fmt(name, s):
    ms = "  ".join("$%s %4.0f%% %s" % (("%dk" % (m // 1000)) if m < 1e6 else "1M", 100 * p,
                                      ("%4.1fmo" % mo) if mo else "   -  ") for m, p, mo in s["milestones"])
    return ("%-34s ruin %4.0f%% | 1st payout %4.0f%% @%sm | end p10/50/90 $%s/$%s/$%s | passes %.1f combines %.1f "
            "xfa-fails %.1f payouts %.1f owner$ avg %.0f p90 %.0f | %s" % (
                name, 100 * s["ruin"], 100 * s["first_payout_p"],
                ("%.1f" % s["first_payout_months"]) if s["first_payout_months"] else "-",
                f"{s['end_p10']:,.0f}", f"{s['end_p50']:,.0f}", f"{s['end_p90']:,.0f}",
                s["passes"], s["combines"], s["xfa_fails"], s["payouts"], s["owner_in"], s["owner_in_p90"], ms))


def load(path):
    with open(path, "rb") as fh:
        return prep(pickle.load(fh))
