"""Alex-style test: aggressive size, max withdrawals, replace failures. Metric = steady-state income per account slot
per month: (avg payouts per funded account - cost per pass) / (avg months per cycle: eval + funded life)."""
import datetime as dt, pickle, statistics as st, sys
sys.path.insert(0, '.')
import firms as F

def slot_income(seq, P, n_eval, n_fund, cushion, step=3, fund_days=252):
    starts = range(0, len(seq) - 300, step)
    tot_pay = tot_cost = tot_days = 0.0
    for s in starts:
        ok, d, cost = F.evaluate(seq[s:], P, n=n_eval)
        tot_cost += cost; tot_days += d
        if ok:
            tot_cost += P["act"]
            got, npay, life = funded_life(seq[s + d:], P, n_fund, cushion, fund_days)
            tot_pay += got; tot_days += life
    months = tot_days / 21
    return (tot_pay - tot_cost) / months if months else 0, tot_pay / len(starts), tot_cost / len(starts)

def funded_life(seq, P, n, cushion, maxd):
    # fixed contracts, withdraw as soon as allowed
    import ladder as L
    bal = hw = 0.0; locked = paid = False; got = 0.0; npay = 0; cyc = []; cyc_days = wins = 0
    for i, p in enumerate(seq[:maxd], 1):
        floor = P["floor_after_payout"] if (paid and P["floor_after_payout"] is not None) else (P["f_lock"] if locked else min(hw - P["f_dd"], P["f_lock"]))
        room = bal - floor
        dll = P["f_dll"] if P["f_dll"] else 1e9
        pnl, breach, near = L.day_pnl(p, n, room, 400 * n, None, 100, dll, bal)
        bal += pnl
        if breach or near: return got, npay, i
        hw = max(hw, bal)
        if hw - P["f_dd"] >= P["f_lock"] or (P.get("lock_at") and bal >= P["lock_at"]): locked = True
        cyc.append(pnl); cyc_days += 1
        if pnl >= P.get("qday", 150): wins += 1
        prof = sum(cyc)
        ok = (wins >= P["ndays"] and prof >= P.get("cycle_min", 1)) if P["rule"] == "days" else (cyc_days >= P["every"] and prof >= P["cycle_min"])
        if ok and P["f_cons"] and prof > 0 and max(cyc) > P["f_cons"] * prof: ok = False
        if ok:
            cap = P["pmax"][min(npay, len(P["pmax"]) - 1)]
            amt = min(cap, P["pfrac"] * max(bal, 0), bal - max(cushion, P["buffer"]))
            if amt >= P["pmin"]:
                bal -= amt; got += amt * P["split"]; npay += 1; paid = True; cyc, cyc_days, wins = [], 0, 0
    return got, npay, maxd

if __name__ == "__main__":
    days = pickle.load(open('/home/claude/data/qqq/v_hourly+vt1.0.pkl', 'rb')); keys = sorted(days)
    periods = {"2024-26": [days[k] for k in keys if k >= dt.date(2024, 1, 2)], "all": [days[k] for k in keys]}
    for name in ("Lucid 50K Flex", "Topstep 50K (Standard)", "MFFU 50K Rapid EOD", "Bulenox 50K Qualification EOD"):
        P = F.PLANS[name]
        rows = []
        for ne in (2, 3, 4):
            for nf in (1, 2, 3, 4):
                for cush in (0, 1000):
                    r = [slot_income(seq, P, ne, nf, cush) for seq in periods.values()]
                    rows.append((r[0][0], r[1][0], ne, nf, cush))
        print("\n" + name + "   $/slot/month: 2024-26 | all-years   (eval contracts, funded contracts, cushion)")
        for a, b, ne, nf, c in sorted(rows, reverse=True)[:5]:
            print("   %+6.0f | %+6.0f   eval %d  funded %d  cushion %d" % (a, b, ne, nf, c))
        base = [x for x in rows if x[2] == 2 and x[3] == 1 and x[4] == 1000][0]
        print("   protective baseline (2 / 1 / 1000): %+6.0f | %+6.0f" % (base[0], base[1]))
