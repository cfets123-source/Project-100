"""Rank automation-friendly futures prop firms by expected profit per evaluation attempt (50K plans).

Rules from the firms' help centers as read 2026-10-22 (see RESULT.md for sources). Generic model:
- Evaluation: EOD-trailing (or static) drawdown, optional daily loss limit that pauses the day, consistency rule that
  raises the target to best_day / c, one-time or monthly price.
- Funded: activation fee, EOD-trailing drawdown that locks at start(+lock) when reached or after the first payout,
  payout eligibility (N qualifying days of >= X, or every K days with cycle profit >= P), min/max per payout,
  max fraction of profit, balance buffer, funded consistency (best day <= c x cycle profit), split.
All accounts run the bot's signal (hourly + vol sizing) with the bot's guards.
"""
import datetime as dt
import pickle
import statistics as st
import sys

sys.path.insert(0, '.')
import ladder as L

PLANS = {
    "Topstep 50K (Standard)": dict(price=49, monthly=True, target=3000, dd=2000, lock_eval=0, dll=1000, cons=0.50,
        act=149, f_dd=2000, f_lock=0, floor_after_payout=0, f_dll=1000, rule="days", ndays=5, qday=150, pmin=125,
        pmax=[2000], pfrac=0.5, buffer=0, f_cons=None, split=0.90, max_funded=5, extra_monthly=14.5),
    "Bulenox 50K Qualification EOD": dict(price=175, monthly=False, target=3000, dd=2500, lock_eval=None, dll=1100,
        cons=None, act=148, f_dd=2500, f_lock=100, lock_at=2600, floor_after_payout=None, f_dll=1100, rule="every",
        every=10, cycle_min=1, pmin=1000, pmax=[1000, 1500, 2000], pfrac=0.5, buffer=2600, f_cons=0.40, split=0.90,
        max_funded=5, extra_monthly=0),
    "FundedNext 50K Rapid Pro": dict(price=170, monthly=False, target=3000, dd=2000, lock_eval=100, dll=None,
        cons=None, act=0, f_dd=2000, f_lock=100, floor_after_payout=None, f_dll=None, rule="every", every=3,
        cycle_min=500, pmin=250, pmax=[1200], pfrac=1.0, buffer=0, f_cons=0.40, split=0.90, max_funded=5,
        extra_monthly=0),
    "FundedNext 50K Flex": dict(price=80, monthly=False, target=2500, dd=1500, lock_eval=100, dll=None, cons=0.40,
        act=0, f_dd=1500, f_lock=100, floor_after_payout=100, f_dll=None, rule="days", ndays=5, qday=200,
        cycle_min=500, pmin=250, pmax=[1500], pfrac=0.5, buffer=0, f_cons=None, split=0.95, max_funded=5,
        extra_monthly=0),
    "Lucid 50K Flex": dict(price=88, monthly=False, target=3000, dd=2000, lock_eval=100, dll=None, cons=0.40,
        act=0, f_dd=2000, f_lock=100, floor_after_payout=100, f_dll=None, rule="days", ndays=5, qday=150,
        cycle_min=1, pmin=500, pmax=[2000], pfrac=0.5, buffer=0, f_cons=None, split=0.90, max_funded=5,
        extra_monthly=0),
    "FTMO 50K Growth": dict(price=119, monthly=True, target=3000, dd=2000, lock_eval=0, dll=None, cons=0.40,
        act=0, f_dd=2000, f_lock=0, floor_after_payout=None, f_dll=1000, rule="days", ndays=4, qday=150,
        pmin=20, pmax=[2500], pfrac=0.5, buffer=0, f_cons=None, split=0.90, max_funded=3, extra_monthly=0),
    "TradeDay 50K Fast Pass": dict(price=95, monthly=True, target=3000, dd=2000, lock_eval=None, dll=None,
        cons=0.45, min_days=3, act=0, f_dd=2000, f_lock=0, floor_after_payout=0, f_dll=None, rule="days", ndays=5,
        qday=150, pmin=250, pmax=[1500], pfrac=0.5, buffer=0, f_cons=0.45, split=0.80, max_funded=5,
        extra_monthly=0),
    "MFFU 50K Rapid EOD": dict(price=135, monthly=False, target=3000, dd=2000, lock_eval=None, dll=None, cons=0.50,
        min_days=2, act=0, f_dd=2000, f_lock=100, floor_after_payout=None, f_dll=None, rule="every", every=1,
        cycle_min=1, pmin=500, pmax=[1e9], pfrac=1.0, buffer=2100, f_cons=None, split=0.90, max_funded=5,
        extra_monthly=0),
}


def evaluate(seq, P, n=2, maxd=126):
    """One evaluation attempt. Returns (passed, days, cost)."""
    bal = hw = best = 0.0
    locked = False
    for i, p in enumerate(seq[:maxd], 1):
        if P["lock_eval"] is not None and locked:
            floor = P["lock_eval"]
        else:
            floor = hw - P["dd"]
            if P["lock_eval"] is not None:
                floor = min(floor, P["lock_eval"])
        room = bal - floor
        dll = P["dll"] if P["dll"] else 1e9
        c = P["cons"]

        def need_fn(ci, bal=bal, best=best):
            need = P["target"] if not c else max(P["target"], max(best, ci) / c)
            return bal + ci >= need
        pnl, breach, near = L.day_pnl(p, n, room, 800, need_fn, 400, dll, bal)
        bal += pnl
        cost_so_far = P["price"] * (1 + (i - 1) // 21) if P["monthly"] else P["price"]
        if breach or near:
            return False, i, cost_so_far
        best = max(best, pnl)
        hw = max(hw, bal)
        if P["lock_eval"] is not None and hw - P["dd"] >= P["lock_eval"]:
            locked = True
        need = P["target"] if not c else max(P["target"], best / c)
        if bal >= need and i >= P.get("min_days", 1):
            return True, i, cost_so_far
    return False, maxd, P["price"] * (1 + (maxd - 1) // 21) if P["monthly"] else P["price"]


def funded(seq, P, per=2500, nmax=2, cushion=2000, maxd=252):
    """One funded account for up to maxd days. Returns total payouts to the trader (after split)."""
    bal = hw = 0.0
    locked = paid = False
    got, npay, cyc, cyc_days, wins = 0.0, 0, [], 0, 0
    for i, p in enumerate(seq[:maxd], 1):
        if paid and P["floor_after_payout"] is not None:
            floor = P["floor_after_payout"]
        elif locked:
            floor = P["f_lock"]
        else:
            floor = min(hw - P["f_dd"], P["f_lock"])
        room = bal - floor
        n = max(1, min(nmax, int(room // per)))
        dll = P["f_dll"] if P["f_dll"] else 1e9
        pnl, breach, near = L.day_pnl(p, n, room, 400 * n, None, 150, dll, bal)
        bal += pnl
        if breach or near:
            break
        hw = max(hw, bal)
        if hw - P["f_dd"] >= P["f_lock"] or (P.get("lock_at") and bal >= P["lock_at"]):
            locked = True
        cyc.append(pnl)
        cyc_days += 1
        if pnl >= P.get("qday", 150):
            wins += 1
        prof = sum(cyc)
        if P["rule"] == "days":
            ok = wins >= P["ndays"] and prof >= P.get("cycle_min", 1)
        else:
            ok = cyc_days >= P["every"] and prof >= P["cycle_min"]
        if ok and P["f_cons"] and prof > 0 and max(cyc) > P["f_cons"] * prof:
            ok = False
        if ok:
            cap = P["pmax"][min(npay, len(P["pmax"]) - 1)]
            amt = min(cap, P["pfrac"] * max(bal, 0), bal - max(cushion, P["buffer"]))
            if amt >= P["pmin"]:
                bal -= amt
                got += amt * P["split"]
                npay += 1
                paid = True
                cyc, cyc_days, wins = [], 0, 0
    return got, npay


def rank(days, keys, label, step=2):
    seq = [days[k] for k in keys]
    out = []
    for name, P in PLANS.items():
        starts = range(0, len(seq) - 130, step)
        ev = [evaluate(seq[s:], P) for s in starts]
        rate = sum(e[0] for e in ev) / len(ev)
        cost = st.mean(e[2] for e in ev)
        passes = [(s, e) for s, e in zip(starts, ev) if e[0]]
        vals = [funded(seq[s + e[1]:], P)[0] for s, e in passes if s + e[1] < len(seq) - 60]
        fv = st.mean(vals) if vals else 0.0
        api = P["extra_monthly"] * 12 / max(1, P["max_funded"])  # spread per account over a year
        ev_attempt = rate * (fv - P["act"] - api) - cost
        out.append((ev_attempt, name, rate, cost, fv, cost / rate + P["act"] if rate else 0))
    print("\n%s" % label)
    print("%-32s %8s %6s %7s %10s %12s" % ("plan", "EV/try", "pass", "cost/try", "funded 1y", "cost/pass"))
    for ev_attempt, name, rate, cost, fv, cpp in sorted(out, reverse=True):
        print("%-32s %+8.0f %5.1f%% %8.0f %10.0f %12.0f" % (name, ev_attempt, 100 * rate, cost, fv, cpp))
    return out


if __name__ == "__main__":
    days = pickle.load(open('/home/claude/data/qqq/v_hourly+vt1.0.pkl', 'rb'))
    keys = sorted(days)
    rank(days, [k for k in keys if k >= dt.date(2024, 1, 2)], "2024-2026 (recent, unseen by strategy tuning)")
    rank(days, [k for k in keys if k <= dt.date(2023, 12, 29)], "2019-2023")
