"""Multi-market core test (research/20261015-multimarket-core/PLAN.md).
Same satellites as the live allocator (rot_curve.run, weekly swap); only the 50% core changes."""
import datetime as dt
import random
import sys

from rot_curve import CL, IND, RULES, SIG, T, run as alloc_run, CURVE as ACURVE

C = .0005
SIGNALS = ["QQQ", "SPY", "IWM", "EFA", "EEM", "TLT", "GLD", "DBC"]
SAFE = "SHY"
LEV = {"QQQ": "TQQQ", "SPY": "UPRO", "IWM": "TNA", "TLT": "TMF"}
DEV = (dt.date(2019, 1, 2), dt.date(2023, 12, 29))
CONF = (dt.date(2024, 1, 2), dt.date(2026, 9, 30))
FULL = (dt.date(2019, 1, 2), dt.date(2026, 9, 30))


def mom(sym, d):
    """126-day return at the close before d."""
    z = CL[sym].get(d)
    if not z:
        return None
    return IND[sym]["mom126"][z[0] - 1]


def pick(d, levered):
    safe_m = mom(SAFE, d) or 0
    ranked = sorted((m, s) for s in SIGNALS if (m := mom(s, d)) is not None)[::-1][:2]
    out = []
    for m, s in ranked:
        v = (LEV.get(s, s) if levered else s) if m > safe_m else SAFE
        out.append(v)
    while len(out) < 2:
        out.append(SAFE)
    return out  # two 25% slots (may repeat SHY)


def run(a, b, levered, core=.5, slots=5, margin=.2):
    curve = []
    days = sorted(d for d in T if a <= d <= b)
    cash, sat, core_pos = 100.0, [], []  # core_pos: list of [sym, qty]
    peak, mdd, ntr, last_week = 100.0, 0.0, 0, None

    def px(sym, d, i):
        z = CL[sym].get(d)
        return z[1][i] if z else None

    def mark(p, d):
        z = CL[p["s"]].get(d)
        return z[1][4] if z else p["last"]

    def core_val(d, i=4):
        return sum(q * (px(s, d, i) or lastp[s]) for s, q in core_pos)

    lastp = {}
    for d in days:
        # satellite exits (identical to live allocator)
        for p in list(sat):
            z = CL[p["s"]].get(d)
            if not z:
                continue
            k, (dd, po, ph, pl, pc, _) = z
            x = None
            if p["exit_next"]:
                x = po
            elif pl <= p["stop"]:
                x = min(po, p["stop"])
            elif ph >= p["tgt"]:
                x = max(po, p["tgt"])
            if x is not None:
                cash += p["q"] * x * (1 - C)
                sat.remove(p)
                continue
            p["last"] = pc
            p["n"] += 1
            R = RULES[p["r"]]
            if p["n"] >= R["hold"] or R["exit"](IND[p["s"]], k):
                p["exit_next"] = True
        # core: first trading day of each ISO week, at the open
        wk = d.isocalendar()[:2]
        if wk != last_week:
            last_week = wk
            want = pick(d, levered)
            keep, new_pos = list(want), []
            for s, q in core_pos:
                if s in keep:
                    keep.remove(s)
                    new_pos.append([s, q])
                else:
                    o = px(s, d, 1) or lastp[s]
                    cash += q * o * (1 - C)
            core_pos = new_pos
            eq_open = cash + core_val(d, 1) + sum(p["q"] * (px(p["s"], d, 1) or p["last"]) for p in sat)
            for s in keep:
                o = px(s, d, 1)
                if not o:
                    continue
                stake = min(cash, eq_open * core / 2)
                if stake < 1:
                    continue
                core_pos.append([s, stake / (o * (1 + C))])
                cash -= stake
        for s, q in core_pos:
            c = px(s, d, 4)
            if c:
                lastp[s] = c
        # satellite entries (identical rules; skip symbols held in the core)
        held = {p["s"] for p in sat} | {s for s, _ in core_pos}
        cands = sorted([z for z in SIG.get(d, []) if z[0] not in held and d in CL[z[0]]], key=lambda z: -z[2])
        seen = set()
        for s, r, m in cands:
            if s in seen:
                continue
            seen.add(s)
            if len(sat) >= slots:
                if d.weekday() != 0:
                    continue

                def cur_mom(p):
                    z = CL[p["s"]].get(d)
                    return (IND[p["s"]]["mom126"][z[0] - 1] or 0) if z else 9
                pool = [p for p in sat if not p["exit_next"]]
                if not pool:
                    continue
                w = min(pool, key=cur_mom)
                if m < cur_mom(w) + margin:
                    continue
                cash += w["q"] * CL[w["s"]][d][1][1] * (1 - C)
                sat.remove(w)
            eq = cash + core_val(d) + sum(p["q"] * mark(p, d) for p in sat)
            st = min(cash, eq * (1 - core) / slots)
            if st < 1:
                break
            po = CL[s][d][1][1] * (1 + C)
            R = RULES[r]
            sat.append(dict(s=s, r=r, q=st / po, e=po, stop=po * (1 - R["stop"]), tgt=po * (1 + R["target"]),
                            n=0, last=po, exit_next=False))
            cash -= st
            ntr += 1
        eq = cash + core_val(d) + sum(p["q"] * mark(p, d) for p in sat)
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
        curve.append((d, eq))
    return eq, mdd, curve


def stress(curve, paths=4000, block=20, horizon=252, seed=7):
    rets = [curve[i][1] / curve[i - 1][1] for i in range(1, len(curve))]
    rng = random.Random(seed)
    hit, ends = 0, []
    for _ in range(paths):
        eq, h, n = 100.0, False, 0
        while n < horizon:
            i = rng.randrange(0, len(rets) - block)
            for m in rets[i:i + block]:
                eq *= m
                n += 1
                h |= eq <= 50
                if n >= horizon:
                    break
        hit += h
        ends.append(eq)
    ends.sort()
    return hit / paths, ends[200], ends[2000], ends[3800]


def crash_low(levered, a, b):
    _, _, cv = run(a, b, levered)
    return min(e for _, e in cv)


if __name__ == "__main__":
    bench = {}
    for lbl, (a, b) in (("dev", DEV), ("conf", CONF)):
        e, m, *_ = alloc_run(a, b, mode="rot", weekly=True)
        bench[lbl] = (e, m)
        print(f"ALLOC {lbl}: ${e:.2f} mdd {m:.1%}")
    for name, lev in (("MC1", False), ("MC2", True)):
        res = {lbl: run(a, b, lev)[:2] for lbl, (a, b) in (("dev", DEV), ("conf", CONF))}
        _, _, full = run(*FULL, lev)
        p, p5, p50, p95 = stress(full)
        lows = {"COVID": crash_low(lev, dt.date(2020, 2, 19), dt.date(2020, 4, 30)),
                "2022": crash_low(lev, dt.date(2022, 1, 3), dt.date(2022, 12, 30))}
        ok1 = all(res[k][0] >= bench[k][0] or (res[k][0] >= .85 * bench[k][0] and res[k][1] <= bench[k][1] - .10)
                  for k in res)
        ok2 = p <= .10 and all(v > 50 for v in lows.values())
        print(f"\n{name}: dev ${res['dev'][0]:.2f} mdd {res['dev'][1]:.1%} | conf ${res['conf'][0]:.2f} mdd {res['conf'][1]:.1%}")
        print(f"  stress p_floor {p:.1%}  12mo p5/p50/p95 ${p5:.0f}/${p50:.0f}/${p95:.0f}  crash lows " +
              ", ".join(f"{k} ${v:.2f}" for k, v in lows.items()))
        print(f"  [{'PASS' if ok1 else 'FAIL'}] return/drawdown vs allocator   [{'PASS' if ok2 else 'FAIL'}] stress gate"
              f"   VERDICT {'PASS' if ok1 and ok2 else 'FAIL'}")
