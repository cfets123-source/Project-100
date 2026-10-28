"""Intraday test (see PLAN.md). Pure standard library.
    python intraday_bt.py <data_dir>
Reads QQQ/TQQQ/SQQQ 5-minute bars (csv.gz from fetch.py) and prints the pre-registered verdict.
"""
import csv
import datetime as dt
import gzip
import random
import sys
from collections import defaultdict
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DEV = (dt.date(2019, 1, 2), dt.date(2023, 12, 29))
CONF = (dt.date(2024, 1, 2), dt.date(2026, 9, 30))
ALLOC = {"dev": 331.0, "conf": 217.0}
CRASHES = (("COVID", dt.date(2020, 2, 19), dt.date(2020, 4, 30)), ("2022", dt.date(2022, 1, 3), dt.date(2022, 12, 30)))
OPEN, LAST = dt.time(9, 30), dt.time(15, 55)
LEV = {"TQQQ": 3.0, "SQQQ": -3.0}


def load(path):
    """{date: {time: (o,h,l,c,v)}} for regular-session bars only."""
    days = defaultdict(dict)
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            t = dt.datetime.fromisoformat(r["t"].replace("Z", "+00:00")).astimezone(ET)
            if OPEN <= t.time() <= LAST:
                days[t.date()][t.time()] = tuple(float(r[k]) for k in "ohlcv")
    return days


def tkey(t):
    return t.hour * 60 + t.minute


def fill_stop(inst_bar, lev, q_open, q_stop):
    """ETF price when QQQ reaches q_stop inside a bar (bar open if QQQ already gapped through)."""
    o = inst_bar[0]
    return o * (1 + lev * (q_stop / q_open - 1))


class Sim:
    """Daily P&L multipliers per strategy; each day is independent (always flat overnight)."""

    def __init__(self, Q, T, S):
        self.Q, self.I = Q, {"TQQQ": T, "SQQQ": S}
        self.days = sorted(d for d in Q if d in T and d in S and dt.time(9, 30) in Q[d] and LAST in Q[d])

    def bars(self, d, sym):
        return self.I[sym][d]

    # ---- ORB5 ----
    def orb(self, d, cost):
        q = self.Q[d]
        o, h, l, c, _ = q[dt.time(9, 30)]
        if c == o or dt.time(9, 35) not in q:
            return 1.0, 0
        long = c > o
        sym = "TQQQ" if long else "SQQQ"
        ib = self.bars(d, sym)
        if dt.time(9, 35) not in ib:
            return 1.0, 0
        q_entry = q[dt.time(9, 35)][0]
        stop = l if long else h
        risk = abs(q_entry - stop)
        if risk <= 0:
            return 1.0, 0
        target = q_entry + 10 * risk if long else q_entry - 10 * risk
        entry = ib[dt.time(9, 35)][0] * (1 + cost)
        lev = LEV[sym]
        exit_px = None
        for t in sorted(x for x in q if dt.time(9, 35) <= x <= LAST):
            if t not in ib:
                continue
            qo, qh, ql, qc, _ = q[t]
            hit_stop = ql <= stop if long else qh >= stop
            hit_tgt = qh >= target if long else ql <= target
            if hit_stop:  # stop checked first (conservative)
                lvl = min(qo, stop) if long else max(qo, stop)
                exit_px = fill_stop(ib[t], lev, qo, lvl)
                break
            if hit_tgt:
                lvl = max(qo, target) if long else min(qo, target)
                exit_px = fill_stop(ib[t], lev, qo, lvl)
                break
        if exit_px is None:
            exit_px = ib[LAST][3] if LAST in ib else ib[max(ib)][3]
        return exit_px * (1 - cost) / entry, 1

    # ---- NOISE ----
    def noise_sigma(self):
        """sigma[d][time] from the previous 14 days' |close(t)/open - 1|."""
        moves = {}
        for d in self.days:
            q = self.Q[d]
            op = q[dt.time(9, 30)][0]
            moves[d] = {t: abs(b[3] / op - 1) for t, b in q.items()}
        sig = {}
        for i, d in enumerate(self.days):
            if i < 14:
                continue
            prev = self.days[i - 14:i]
            sig[d] = {}
            for t in self.Q[d]:
                vals = [moves[p][t] for p in prev if t in moves[p]]
                if len(vals) >= 10:
                    sig[d][t] = sum(vals) / len(vals)
        return sig

    def noise(self, d, cost, sig, prev_close):
        if d not in sig or prev_close is None:
            return 1.0, 0
        q = self.Q[d]
        op = q[dt.time(9, 30)][0]
        times = sorted(q)
        pv = vol = 0.0
        vwap = {}
        for t in times:
            o, h, l, c, v = q[t]
            pv += (h + l + c) / 3 * v
            vol += v
            vwap[t] = pv / vol if vol else c
        checks = [t for t in times if t.minute in (25, 55) and dt.time(9, 55) <= t <= dt.time(15, 25)]
        # a check "at 10:00" uses the bar that closes at 10:00 (starts 9:55); orders fill at the next bar open
        mult, trades, pos = 1.0, 0, None  # pos = (sym, entry_price)
        for t in checks:
            if t not in sig[d]:
                continue
            s = sig[d][t]
            up = max(op, prev_close) * (1 + s)
            dn = min(op, prev_close) * (1 - s)
            c = q[t][3]
            nxt = dt.time(*divmod(tkey(t) + 5, 60))
            if pos:
                sym, ent = pos
                out = c < max(up, vwap[t]) if sym == "TQQQ" else c > min(dn, vwap[t])
                ib = self.bars(d, sym)
                if out and nxt in ib:
                    mult *= ib[nxt][0] * (1 - cost) / ent
                    pos = None
            if pos is None:
                sym = "TQQQ" if c > up else "SQQQ" if c < dn else None
                if sym:
                    ib = self.bars(d, sym)
                    if nxt in ib:
                        pos = (sym, ib[nxt][0] * (1 + cost))
                        trades += 1
        if pos:
            sym, ent = pos
            ib = self.bars(d, sym)
            mult *= (ib[LAST][3] if LAST in ib else ib[max(ib)][3]) * (1 - cost) / ent
        return mult, trades

    def run(self, name, cost):
        out = {}
        sig = self.noise_sigma() if name == "NOISE" else None
        prev_close = None
        for d in self.days:
            if name == "ORB5":
                m, n = self.orb(d, cost)
            else:
                m, n = self.noise(d, cost, sig, prev_close)
            prev_close = self.Q[d][LAST][3]
            out[d] = (m, n)
        return out


def window(daily, a, b, start=100.0):
    eq, peak, mdd, n, wins, tdays = start, start, 0.0, 0, 0, 0
    low = start
    for d in sorted(daily):
        if a <= d <= b:
            m, k = daily[d]
            eq *= m
            n += k
            if k:
                tdays += 1
                wins += m > 1
            peak = max(peak, eq)
            low = min(low, eq)
            mdd = max(mdd, 1 - eq / peak)
    return {"end": round(eq, 2), "mdd": round(mdd, 3), "trades": n, "win": round(wins / tdays, 3) if tdays else 0,
            "low": round(low, 2)}


def stress(daily, paths=4000, block=20, horizon=252, floor=50.0, seed=7):
    rets = [daily[d][0] for d in sorted(daily)]
    rng = random.Random(seed)
    touch, ends = 0, []
    for _ in range(paths):
        eq, hit = 100.0, False
        steps = 0
        while steps < horizon:
            i = rng.randrange(0, len(rets) - block)
            for m in rets[i:i + block]:
                eq *= m
                steps += 1
                if eq <= floor:
                    hit = True
                if steps >= horizon:
                    break
        touch += hit
        ends.append(eq)
    ends.sort()
    pct = lambda p: round(ends[int(p * (len(ends) - 1))], 2)
    return {"p_floor": round(touch / paths, 4), "p5": pct(.05), "p50": pct(.5), "p95": pct(.95)}


def main(data_dir):
    Q, T, S = (load(f"{data_dir}/{s}_5m.csv.gz") for s in ("QQQ", "TQQQ", "SQQQ"))
    sim = Sim(Q, T, S)
    print(f"DATA sessions={len(sim.days)} {sim.days[0]}..{sim.days[-1]}")
    verdicts = {}
    for name in ("ORB5", "NOISE"):
        base, hi = sim.run(name, .0003), sim.run(name, .0006)
        dev, conf = window(base, *DEV), window(base, *CONF)
        dev6, conf6 = window(hi, *DEV), window(hi, *CONF)
        st = stress(base)
        crash = {lbl: window(base, a, b)["low"] for lbl, a, b in CRASHES}
        checks = {
            "above $100 both": dev["end"] > 100 and conf["end"] > 100,
            "beats allocator both": dev["end"] > ALLOC["dev"] and conf["end"] > ALLOC["conf"],
            "above $100 at 0.06%": dev6["end"] > 100 and conf6["end"] > 100,
            "stress gate": st["p_floor"] <= .10 and all(v > 50 for v in crash.values()),
        }
        verdicts[name] = all(checks.values())
        print(f"\n{name}")
        print(f"  dev  2019-2023 : {dev}")
        print(f"  conf 2024-Sep26: {conf}")
        print(f"  at 0.06% cost  : dev ${dev6['end']}  conf ${conf6['end']}")
        print(f"  stress 12 mo   : {st}   crash lows {crash}")
        for k, v in checks.items():
            print(f"  [{'PASS' if v else 'FAIL'}] {k}")
        print(f"  VERDICT {name}: {'PASS' if verdicts[name] else 'FAIL'}")
    passed = [n for n, v in verdicts.items() if v]
    print("\nRESULT:", "PASS " + ",".join(passed) if passed else "FAIL (no candidate met the pre-registered rule)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/data/research/intraday")
