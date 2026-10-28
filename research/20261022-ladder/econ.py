"""Single-account economics: one Combine attempt and one funded account, from every historical start day."""
import statistics as st, sys
sys.path.insert(0, '.')
import ladder as L

def combine(seq, n, T, maxd=126):
    bal = hw = best = 0.0; locked = False
    for i, p in enumerate(seq[:maxd], 1):
        floor = 0.0 if locked else min(0.0, hw - T["mll"])
        room = bal - floor
        def need_fn(ci, bal=bal, best=best): return bal + ci >= max(T["target"], max(best, ci) / L.CONSISTENCY)
        pnl, breach, near = L.day_pnl(p, n, room, T["stop"] * n / T["n"], need_fn, T["buffer"], T["dll"], bal)
        bal += pnl
        if breach or near: return "fail", i
        best = max(best, pnl); hw = max(hw, bal); locked = locked or hw - T["mll"] >= 0
        if bal >= max(T["target"], best / L.CONSISTENCY): return "pass", i
    return "timeout", maxd

def xfa(seq, n, T, path="standard", frac=0.5, cushion=0.0, maxd=504):
    bal = hw = 0.0; locked = paid = False; wins = 0; got = 0.0; npay = 0
    for i, p in enumerate(seq[:maxd], 1):
        floor = 0.0 if (locked or paid) else min(0.0, hw - T["mll"])
        room = bal - floor
        pnl, breach, near = L.day_pnl(p, n, room, T["stop"] * n / T["n"], None, T["buffer"], T["dll"], bal)
        bal += pnl
        if breach or near: return got, npay, i, "fail"
        hw = max(hw, bal); locked = locked or hw - T["mll"] >= 0
        if pnl >= 150: wins += 1
        ok = wins >= 5
        if ok:
            amt = min(frac * bal, 0.5 * bal, T["cap"])
            if amt >= 125 and bal - amt >= cushion:
                bal -= amt; got += amt * L.SPLIT; npay += 1; wins = 0; paid = True; hw = bal
    return got, npay, maxd, "alive"

if __name__ == "__main__":
    days = L.load('/home/claude/data/qqq/noise_days.pkl'); keys = sorted(days)
    seq = [days[k] for k in keys]
    T = L.TYPES[50]
    starts = range(0, len(seq) - 130, 3)
    print("COMBINE 50K (fee $49/mo):  n  pass%  medDays  fees/attempt")
    for n in (1, 2, 3, 4, 5, 6):
        r = [combine(seq[s:], n, T) for s in starts]
        ps = [d for o, d in r if o == "pass"]; rate = len(ps) / len(r)
        fees = st.mean(49 * (1 + (d - 1) // 21) for o, d in r)
        print("   %d  %5.1f%%  %4.0f   $%5.0f   cost per pass $%.0f" % (n, 100 * rate, st.median(ps) if ps else 0, fees, (fees / rate + 149) if rate else 0))
    print("\nFUNDED 50K: n  cushion  avg payouts$  median$  p(any payout)  median life days  alive at 2y")
    xs = range(0, len(seq) - 510, 3)
    for n in (1, 2, 3):
        for cush in (0, 1000, 2000):
            r = [xfa(seq[s:], n, T, cushion=cush) for s in xs]
            g = [x[0] for x in r]
            print("   %d  %5d   $%6.0f  $%6.0f   %5.1f%%   %4.0f   %4.1f%%" % (n, cush, st.mean(g), st.median(g), 100 * sum(x[1] > 0 for x in r) / len(r), st.median(x[2] for x in r), 100 * sum(x[3] == "alive" for x in r) / len(r)))
