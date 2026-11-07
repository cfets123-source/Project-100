"""The 7-point checklist answered by code (news cannot be checked historically -> assumed clear).
Scores every set-and-forget candidate, then compares 'take if score >= k' against taking everything."""
import datetime as dt, glob, os, statistics as st
import sf

def scored(sym, rows, piv=3, lookback=60, rr=3.0, maxhold=20):
    d = [r[0] for r in rows]; o = [r[1] for r in rows]; h = [r[2] for r in rows]; l = [r[3] for r in rows]; c = [r[4] for r in rows]
    e20, e100 = sf.ema(c, 20), sf.ema(c, 100); cost = sf.DEF_COST
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(rows))]
    atr = sf.ema(tr, 14); out = []
    for i in range(lookback + piv + 6, len(rows) - 1):
        rng = h[i] - l[i]
        if rng <= 0: continue
        tol = 0.25 * atr[i - 1]; body = abs(c[i] - o[i]) or 1e-12
        sups = [l[j] for j in range(i - lookback, i - piv) if l[j] == min(l[j - piv:j + piv + 1])]
        ress = [h[j] for j in range(i - lookback, i - piv) if h[j] == max(h[j - piv:j + piv + 1])]
        for side in (1, -1):
            lv = [s for s in (sups if side > 0 else ress) if (l[i] <= s + tol and c[i] > s) if side > 0] if side > 0 else \
                 [r for r in ress if h[i] >= r - tol and c[i] < r]
            if not lv: continue
            wick = (min(o[i], c[i]) - l[i]) if side > 0 else (h[i] - max(o[i], c[i]))
            if wick < 0.5 * rng: continue
            level = lv[-1]
            ent = o[i + 1]; sl = (l[i] - 0.1 * atr[i]) if side > 0 else (h[i] + 0.1 * atr[i]); risk = (ent - sl) * side
            if risk <= 0 or risk > 3 * atr[i]: continue
            tp = ent + side * rr * risk
            # ---- checklist ----
            touches = sum(1 for j in range(i - lookback, i) if (abs(l[j] - level) <= tol if side > 0 else abs(h[j] - level) <= tol))
            q1 = touches >= 3                                            # level held at least twice before (+ the pivot)
            q2 = (c[i] > e100[i] and e100[i] > e100[i - 5]) if side > 0 else (c[i] < e100[i] and e100[i] < e100[i - 5])
            q3 = wick >= 2 * body and ((c[i] - l[i]) >= 0.67 * rng if side > 0 else (h[i] - c[i]) >= 0.67 * rng)
            move = (c[i - 5] - c[i - 1]) * side                          # price came INTO the level
            path_len = sum(abs(c[j] - c[j - 1]) for j in range(i - 4, i)) or 1e-12
            q4 = move >= 1.0 * atr[i] and move / path_len >= 0.5
            opp = [x for x in (ress if side > 0 else sups) if (x - ent) * side > 0]
            q5 = not opp or min((x - ent) * side for x in opp) >= rr * risk
            q2b = (c[i] > e20[i]) if side > 0 else (c[i] < e20[i])
            res_r, exit_i = None, None
            for k in range(i + 1, min(len(rows), i + 1 + maxhold)):
                if (l[k] <= sl) if side > 0 else (h[k] >= sl): res_r, exit_i = -1.0, k; break
                if (h[k] >= tp) if side > 0 else (l[k] <= tp): res_r, exit_i = rr, k; break
            if res_r is None: exit_i = min(len(rows) - 1, i + maxhold); res_r = (c[exit_i] - ent) * side / risk
            res_r -= 2 * cost * ent / risk
            out.append({"sym": sym, "date": d[i + 1], "exit": d[exit_i], "side": side, "r": res_r,
                        "q": [q1, q2, q3, q4, q5], "ema20": q2b, "cost_r": 2 * cost * ent / risk})
    return out

CCY = lambda s: (s[:3], s[3:])
def no_doubling(trs):
    """Checklist #7: skip a trade if an open trade already bets the same currency in the same direction."""
    keep, open_ = [], []
    for t in sorted(trs, key=lambda t: t["date"]):
        open_ = [x for x in open_ if x["exit"] >= t["date"]]
        b, q = CCY(t["sym"]); exp = {b: t["side"], q: -t["side"]}
        clash = any(e2.get(k) == v for x in open_ for e2 in [{CCY(x["sym"])[0]: x["side"], CCY(x["sym"])[1]: -x["side"]}]
                    for k, v in exp.items() if k != "USD" or True)
        if clash: continue
        keep.append(t); open_.append(t)
    return keep

def line(trs, label):
    if not trs: return "%-40s no trades" % label
    r = [t["r"] for t in trs]; w = [x for x in r if x > 0]; ls = [x for x in r if x <= 0]
    return "%-40s trades %4d (%4.1f/mo)  win %4.1f%%  avg R %+.2f  PF %.2f" % (
        label, len(r), len(r) / 12 / 6.8 if trs[0]["date"].year >= 2020 else len(r) / 12 / 10, 100 * len(w) / len(r), st.mean(r),
        sum(w) / -sum(ls) if ls else 99)

data = {os.path.basename(p)[:-4]: sf.load(p) for p in sorted(glob.glob("/home/claude/fx/*.csv"))}
allc = []
for s, rows in data.items(): allc += scored(s, rows)
split = dt.date(2019, 12, 31)
for k in (0, 3, 4, 5):
    sel = [t for t in allc if sum(t["q"]) >= k]
    sel = no_doubling(sel)
    print("score >= %d of 5 checks (+ no doubling, news assumed clear)" % k)
    print("  " + line([t for t in sel if t["date"] <= split], "2010-2019"))
    print("  " + line([t for t in sel if t["date"] > split], "2020-2026"))
    print("  " + line([t for t in sel if t["date"] >= dt.date(2026, 7, 29)], "last 3 months"))
print("\nEach check alone (all years): avg R when YES vs NO")
for n, name in enumerate(["1 strong level", "2 weekly trend", "3 clean rejection", "4 clean move in", "5 room to target"]):
    y = [t["r"] for t in allc if t["q"][n]]; no = [t["r"] for t in allc if not t["q"][n]]
    print("  %-18s YES %+.3f (%d)   NO %+.3f (%d)" % (name, st.mean(y), len(y), st.mean(no), len(no)))
print("  median spread cost per trade: %.2f R" % st.median(t["cost_r"] for t in allc))
