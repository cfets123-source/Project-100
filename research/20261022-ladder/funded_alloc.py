"""Track total FUNDED ACCOUNT SIZE (allocation) - what prop traders call '$X funded' - in the multi-firm ladder."""
import datetime as dt, pickle, random, statistics as st, sys
sys.path.insert(0, '.')
import ladder as L, ladder2 as L2
days = pickle.load(open('/home/claude/data/qqq/v_hourly+vt1.0.pkl', 'rb')); keys = sorted(days)
recent = [k for k in keys if k >= dt.date(2024, 1, 2)]
def size(a): return 150000 if "150K" in a.plan else 50000
for budget in (400, 1000):
    for label, ks in (("2024-26", recent), ("all years", keys)):
        rng = random.Random(7); hits = {100000: [], 1000000: []}; n = 120
        for _ in range(n):
            lad = L2.Ladder2(budget=budget); seen = set()
            for d, p in enumerate(L.bootstrap(ks, days, 504, rng), 1):
                lad.step(p)
                alloc = sum(size(a) for a in lad.live(stage="funded"))
                for m in hits:
                    if m not in seen and alloc >= m: hits[m].append(d); seen.add(m)
                if lad.ruined(): break
        out = []
        for m, h in hits.items():
            h.sort()
            out.append("$%s funded: %3.0f%% (fastest 10%%: %s mo, median %s mo)" % (
                "100K" if m == 100000 else "1M", 100 * len(h) / n,
                ("%.1f" % (h[max(0, int(0.1 * n) - 1)] / 21)) if len(h) >= 0.1 * n else "-",
                ("%.1f" % (st.median(h) / 21)) if h else "-"))
        print("$%d owner money, %s: " % (budget, label) + " | ".join(out), flush=True)
