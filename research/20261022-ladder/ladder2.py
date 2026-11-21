"""Multi-firm ladder, aggressive policy, staged cash (everything after day 0 is paid from payouts).

Every account trades the same daily signal path, so accounts across firms win and lose together.
Start: one Topstep 50K Combine already paid; owner money only for the first $149 activation (budget).
Purchases: highest-earning firm first, one new evaluation per firm at a time, within each firm's funded cap.
Relay subscription ($41.65/mo + $10 per extra live account) starts with the first non-Topstep account.
"""
import datetime as dt
import pickle
import random
import statistics as st
import sys

sys.path.insert(0, '.')
import firms as F
import ladder as L
import aggressive150  # noqa: F401  (adds the 150K plans to F.PLANS)

F.PLANS["FTMO 150K Growth"] = dict(price=229, monthly=True, target=9000, dd=5000, lock_eval=0, dll=None, cons=0.40,
    act=0, f_dd=5000, f_lock=0, floor_after_payout=None, f_dll=3000, rule="days", ndays=4, qday=300, pmin=20,
    pmax=[4000], pfrac=0.5, buffer=0, f_cons=None, split=0.90, max_funded=3, extra_monthly=0)

# firm -> (50K plan, 150K plan, contracts eval/funded at 50K, at 150K, cushion, funded cap, relay?)
FIRMS = [
    ("MFFU", "MFFU 50K Rapid EOD", "MFFU 150K Rapid EOD", (4, 3), (4, 6), 1000, 3, True),
    ("Lucid", "Lucid 50K Flex", "Lucid 150K Flex", (4, 3), (9, 3), 1000, 5, True),
    ("Topstep", "Topstep 50K (Standard)", "Topstep 150K (Standard)", (4, 2), (4, 6), 1000, 5, False),
    ("FTMO", "FTMO 50K Growth", "FTMO 150K Growth", (4, 2), (6, 4), 1000, 3, True),
    ("Bulenox", "Bulenox 50K Qualification EOD", None, (4, 2), None, 1000, 5, True),
]
RELAY_BASE, RELAY_EXTRA, API_TOPSTEP = 41.65, 10.0, 14.50


class Account:
    def __init__(self, firm, plan, n_eval, n_fund, cushion):
        self.firm, self.P, self.ne, self.nf, self.cush = firm, F.PLANS[plan], n_eval, n_fund, cushion
        self.plan = plan
        self.stage = "eval"
        self.bal = self.hw = self.best = 0.0
        self.locked = self.paid = False
        self.days = 0
        self.cyc, self.cyc_days, self.wins, self.npay = [], 0, 0, 0
        self.dead = False

    def step(self, path):
        """Returns (cash_out_to_owner, cost) for the day."""
        P = self.P
        self.days += 1
        cost = 0.0
        if self.stage == "eval":
            if P["monthly"] and self.days > 1 and (self.days - 1) % 21 == 0:
                cost += P["price"]
            floor = P["lock_eval"] if (P["lock_eval"] is not None and self.locked) else (
                min(self.hw - P["dd"], P["lock_eval"]) if P["lock_eval"] is not None else self.hw - P["dd"])
            room = self.bal - floor
            c, bal, best = P["cons"], self.bal, self.best

            def need_fn(ci):
                need = P["target"] if not c else max(P["target"], max(best, ci) / c)
                return bal + ci >= need
            pnl, breach, near = L.day_pnl(path, self.ne, room, 800 * self.ne / 2, need_fn, 400,
                                          P["dll"] or 1e9, self.bal)
            self.bal += pnl
            if breach or near:
                self.dead = True
                return 0.0, cost
            self.best = max(self.best, pnl)
            self.hw = max(self.hw, self.bal)
            if P["lock_eval"] is not None and self.hw - P["dd"] >= P["lock_eval"]:
                self.locked = True
            need = P["target"] if not c else max(P["target"], self.best / c)
            if self.bal >= need and self.days >= P.get("min_days", 1):
                self.stage = "pass"   # waiting for activation
            return 0.0, cost
        if self.stage != "funded":
            return 0.0, 0.0
        floor = P["floor_after_payout"] if (self.paid and P["floor_after_payout"] is not None) else (
            P["f_lock"] if self.locked else min(self.hw - P["f_dd"], P["f_lock"]))
        room = self.bal - floor
        pnl, breach, near = L.day_pnl(path, self.nf, room, 400 * self.nf, None, 100, P["f_dll"] or 1e9, self.bal)
        self.bal += pnl
        if breach or near:
            self.dead = True
            return 0.0, 0.0
        self.hw = max(self.hw, self.bal)
        if self.hw - P["f_dd"] >= P["f_lock"] or (P.get("lock_at") and self.bal >= P["lock_at"]):
            self.locked = True
        self.cyc.append(pnl)
        self.cyc_days += 1
        if pnl >= P.get("qday", 150):
            self.wins += 1
        prof = sum(self.cyc)
        ok = (self.wins >= P["ndays"] and prof >= P.get("cycle_min", 1)) if P["rule"] == "days" else (
            self.cyc_days >= P["every"] and prof >= P["cycle_min"])
        if ok and P["f_cons"] and prof > 0 and max(self.cyc) > P["f_cons"] * prof:
            ok = False
        if ok:
            cap = P["pmax"][min(self.npay, len(P["pmax"]) - 1)]
            amt = min(cap, P["pfrac"] * max(self.bal, 0), self.bal - max(self.cush, P["buffer"]))
            if amt >= P["pmin"]:
                self.bal -= amt
                self.npay += 1
                self.paid = True
                self.cyc, self.cyc_days, self.wins = [], 0, 0
                return amt * P["split"], 0.0
        return 0.0, 0.0


class Ladder2:
    def __init__(self, budget=149.0, big_at=3000.0, reserve=300.0, firms=FIRMS, withdraw_after=None,
                 withdraw_frac=0.0, safe_until=0.0, safe_sizes=(2, 1)):
        self.cash, self.budget, self.owner_in = 0.0, budget, 0.0
        self.big_at, self.reserve, self.firms = big_at, reserve, firms
        self.accts = [Account("Topstep", "Topstep 50K (Standard)", 4, 2, 1000)]
        self.spent = 49.0
        self.t = 0
        self.paid_out = 0.0
        self.withdrawn = 0.0
        self.withdraw_after, self.withdraw_frac = withdraw_after, withdraw_frac
        self.month_income = []
        self._month = 0.0
        self.broke = False
        self.safe_until, self.safe_sizes = safe_until, safe_sizes
        if safe_until > 0:
            self.accts[0].ne, self.accts[0].nf = safe_sizes

    def pay(self, amt):
        if self.cash < amt:
            short = amt - max(self.cash, 0)
            if self.owner_in + short > self.budget:
                return False
            self.owner_in += short
            self.cash += short
        self.cash -= amt
        self.spent += amt
        return True

    def can(self, amt):
        return max(self.cash, 0) + (self.budget - self.owner_in) >= amt

    def live(self, firm=None, stage=None):
        return [a for a in self.accts if not a.dead and (firm is None or a.firm == firm)
                and (stage is None or a.stage == stage)]

    def step(self, path):
        self.t += 1
        # fixed monthly costs
        if self.t % 21 == 0:
            n_relay_live = sum(1 for a in self.live() if a.firm != "Topstep" and a.stage == "funded")
            relay = (RELAY_BASE + RELAY_EXTRA * max(0, n_relay_live - 1)) if any(
                a.firm != "Topstep" for a in self.live()) else 0.0
            if not self.pay(API_TOPSTEP + relay):
                self.broke = True
            self.month_income.append(self._month)
            self._month = 0.0
        for a in self.accts:
            if a.dead:
                continue
            out, cost = a.step(path)
            if cost and not self.pay(cost):
                a.dead = True
            if out:
                self.cash += out
                self.paid_out += out
                self._month += out
        # activations
        if self.safe_until and self.paid_out >= self.safe_until:   # cushion built: switch to aggressive sizing
            for a in self.live():
                s = next(f for f in self.firms if f[0] == a.firm)
                ne, nf = s[4] if (s[2] and a.plan == s[2]) else s[3]
                a.ne, a.nf = max(a.ne, ne), max(a.nf, nf)
        for a in self.live(stage="pass"):
            cap = next(f[6] for f in self.firms if f[0] == a.firm)
            if len(self.live(a.firm, "funded")) >= cap:
                a.dead = True
                continue
            if self.can(a.P["act"]):
                self.pay(a.P["act"])
                a.stage = "funded"
        # owner withdrawals once the stack is built
        if self.withdraw_after and len(self.live(stage="funded")) >= self.withdraw_after and self.cash > self.reserve:
            w = (self.cash - self.reserve) * self.withdraw_frac
            self.cash -= w
            self.withdrawn += w
        self.buy()

    def buy(self):
        for firm, p50, p150, s50, s150, cush, cap, relay in self.firms:
            alive = self.live(firm)
            if any(a.stage in ("eval", "pass") for a in alive) or len(self.live(firm, "funded")) >= cap:
                continue
            big = p150 is not None and self.cash >= self.big_at
            plan, (ne, nf) = (p150, s150) if big else (p50, s50)
            if self.paid_out < self.safe_until:      # protect the bankroll until payouts have built a cushion
                plan, (ne, nf) = p50, self.safe_sizes
            P = F.PLANS[plan]
            need = P["price"] + P["act"] + self.reserve
            if relay and not any(a.firm != "Topstep" for a in self.live()):
                need += RELAY_BASE
            nothing = not self.live()
            if self.cash < need and not (nothing and self.can(P["price"] + P["act"])):
                continue
            if not self.pay(P["price"]):
                continue
            self.accts.append(Account(firm, plan, ne, nf, cush))

    def wealth(self):
        return self.cash + self.withdrawn - self.owner_in

    def ruined(self):
        return self.broke or (not self.live() and not self.can(49 + 149))


def run(paths, **kw):
    lad = Ladder2(**kw)
    hits = {}
    for d, p in enumerate(paths, 1):
        lad.step(p)
        w = lad.wealth()
        for m in (1000, 10000, 100000, 1000000):
            if m not in hits and w >= m:
                hits[m] = d
        mi = lad.month_income[-3:]
        if "1k_day" not in hits and len(mi) == 3 and sum(mi) / 3 >= 21000:
            hits["1k_day"] = d
        if lad.ruined():
            return {"hits": hits, "ruin": d, "end": lad.wealth(), "lad": lad}
    return {"hits": hits, "ruin": None, "end": lad.wealth(), "lad": lad}


def report(label, res, horizon):
    n = len(res)
    def m(key):
        h = [r["hits"][key] for r in res if key in r["hits"]]
        return "%3.0f%% %s" % (100 * len(h) / n, ("@%4.1fmo" % (st.median(h) / 21)) if h else "   -   ")
    inc = []
    for r in res:
        mi = r["lad"].month_income
        inc.append(sum(mi[-6:]) / 6 if len(mi) >= 6 else 0)
    inc.sort()
    ends = sorted(r["end"] for r in res)
    print("%-30s ruin %3.0f%% | $1k %s | $10k %s | $100k %s | $1M %s | $1k/day income %s | income/mo last 6m p25/50/75 "
          "$%s/$%s/$%s | end p50 $%s" % (
              label, 100 * sum(r["ruin"] is not None for r in res) / n, m(1000), m(10000), m(100000), m(1000000),
              m("1k_day"), f"{inc[n // 4]:,.0f}", f"{inc[n // 2]:,.0f}", f"{inc[3 * n // 4]:,.0f}",
              f"{ends[n // 2]:,.0f}"), flush=True)


if __name__ == "__main__":
    days = pickle.load(open('/home/claude/data/qqq/v_hourly+vt1.0.pkl', 'rb'))
    keys = sorted(days)
    recent = [k for k in keys if k >= dt.date(2024, 1, 2)]
    H, N = int(sys.argv[1]) if len(sys.argv) > 1 else 756, int(sys.argv[2]) if len(sys.argv) > 2 else 200
    for budget in (400, 1000):
        for safe in (0, 1500, 4000):
            for label, ks in (("2024-26", recent), ("all years", keys)):
                rng = random.Random(7)
                res = [run(L.bootstrap(ks, days, H, rng), budget=budget, safe_until=safe) for _ in range(N)]
                report("$%d, safe until $%d paid, %s" % (budget, safe, label), res, H)
