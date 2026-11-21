"""Alex G-style 'set and forget' swing rules, made mechanical, on daily gold + 13 FX pairs (2010 -> 2026-10-29).
Long: price tests a daily support level (recent confirmed swing low), rejects it (long lower wick, closes back above),
and is on the right side of the EMA. Enter next open, stop under the rejection low (-0.1 ATR), target = RR x risk.
Orders are left alone until stop or target (max 20 days). Shorts mirrored. Costs: spread per side."""
import csv, datetime as dt, glob, os, statistics as st, sys
COST = {"XAUUSD": 0.00012}; DEF_COST = 0.00012   # ~1.2 bp per side (1-2 pips majors, wider crosses, gold $0.5)

def load(path):
    rows = []
    with open(path) as f:
        r = csv.DictReader(f)
        for x in r:
            rows.append((dt.date.fromisoformat(x["Date"][:10]), float(x["Open"]), float(x["High"]), float(x["Low"]), float(x["Close"])))
    return rows

def ema(vals, n):
    k, out, e = 2 / (n + 1), [], None
    for v in vals:
        e = v if e is None else e + k * (v - e); out.append(e)
    return out

def trades(sym, rows, ema_n=20, piv=3, lookback=60, wick=0.5, tol_atr=0.25, rr=3.0, maxhold=20, trend=True):
    d = [r[0] for r in rows]; o = [r[1] for r in rows]; h = [r[2] for r in rows]; l = [r[3] for r in rows]; c = [r[4] for r in rows]
    e = ema(c, ema_n); cost = COST.get(sym, DEF_COST)
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(rows))]
    atr = ema(tr, 14)
    out, busy_until = [], -1
    for i in range(lookback + piv + 2, len(rows) - 1):
        if i <= busy_until: continue
        rng = h[i] - l[i]
        if rng <= 0: continue
        sup = [l[j] for j in range(i - lookback, i - piv) if l[j] == min(l[j - piv:j + piv + 1])]
        res = [h[j] for j in range(i - lookback, i - piv) if h[j] == max(h[j - piv:j + piv + 1])]
        tol = tol_atr * atr[i - 1]
        side = 0
        if (not trend or c[i] > e[i]) and any(l[i] <= s + tol and c[i] > s for s in sup) and (min(o[i], c[i]) - l[i]) >= wick * rng:
            side = 1
        elif (not trend or c[i] < e[i]) and any(h[i] >= r - tol and c[i] < r for r in res) and (h[i] - max(o[i], c[i])) >= wick * rng:
            side = -1
        if not side: continue
        ent = o[i + 1]
        sl = (l[i] - 0.1 * atr[i]) if side > 0 else (h[i] + 0.1 * atr[i])
        risk = (ent - sl) * side
        if risk <= 0 or risk > 3 * atr[i]: continue
        tp = ent + side * rr * risk
        res_r, exit_i = None, None
        for k in range(i + 1, min(len(rows), i + 1 + maxhold)):
            hit_sl = l[k] <= sl if side > 0 else h[k] >= sl
            hit_tp = h[k] >= tp if side > 0 else l[k] <= tp
            if hit_sl: res_r, exit_i = -1.0, k; break          # stop first if both in one day (conservative)
            if hit_tp: res_r, exit_i = rr, k; break
        if res_r is None:
            exit_i = min(len(rows) - 1, i + maxhold); res_r = (c[exit_i] - ent) * side / risk
        res_r -= 2 * cost * ent / risk                         # spread in R
        # worst open R per day while in the trade (for daily-loss / max-loss checks)
        path = []
        for k in range(i + 1, exit_i + 1):
            adverse = (l[k] - ent) / risk if side > 0 else (ent - h[k]) / risk
            close_r = (c[k] - ent) * side / risk
            path.append((d[k], max(-1.0, adverse), close_r))
        out.append({"sym": sym, "date": d[i + 1], "exit": d[exit_i], "r": res_r, "side": side, "path": path})
        busy_until = exit_i
    return out

def summarize(tr, label):
    if not tr: return "%-34s no trades" % label
    r = [t["r"] for t in tr]; w = [x for x in r if x > 0]; ls = [x for x in r if x <= 0]
    pf = sum(w) / -sum(ls) if ls else 99
    return "%-34s trades %4d  win %4.1f%%  avg R %+.2f  PF %.2f  total R %+6.1f" % (label, len(r), 100 * len(w) / len(r), st.mean(r), pf, sum(r))

def challenge(tr, start, risk=0.01, target=0.10, max_loss=0.10, daily=0.05, maxdays=365):
    """One-step forex prop challenge on the whole portfolio from `start`. Fixed risk per trade as % of initial balance."""
    act = [t for t in tr if t["date"] >= start]
    if not act: return "none", 0
    days = sorted({p[0] for t in act for p in t["path"]})
    days = [x for x in days if x <= start + dt.timedelta(days=maxdays)]
    bal = 0.0; prev_close_eq = 0.0
    for n, day in enumerate(days, 1):
        realized = sum(risk * t["r"] for t in act if t["exit"] < day)
        openw, openc = 0.0, 0.0
        for t in act:
            if t["date"] <= day <= t["exit"]:
                for (pd_, adv, cr) in t["path"]:
                    if pd_ == day:
                        if day == t["exit"]: openw += risk * min(adv, t["r"]); openc += risk * t["r"]
                        else: openw += risk * adv; openc += risk * cr
        worst = realized + openw; close_eq = realized + openc
        if worst <= -max_loss or worst - prev_close_eq <= -daily: return "fail", n
        if close_eq >= target and not any(t["date"] <= day < t["exit"] for t in act): return "pass", n
        prev_close_eq = close_eq
    return "timeout", len(days)

if __name__ == "__main__":
    data = {os.path.basename(p)[:-4]: load(p) for p in sorted(glob.glob("/home/claude/fx/*.csv"))}
    split = dt.date(2019, 12, 31); recent = dt.date(2026, 7, 29)
    for name, kw in (("EMA20 trend, wick 50%, 1:3", {}), ("EMA50 trend, 1:3", {"ema_n": 50}), ("no trend filter, 1:3", {"trend": False}),
                     ("EMA20, 1:2", {"rr": 2.0}), ("EMA20, wick 60%, 1:3", {"wick": 0.6})):
        allt = []
        for s, rows in data.items(): allt += trades(s, rows, **kw)
        allt.sort(key=lambda t: t["date"])
        dev = [t for t in allt if t["date"] <= split]; conf = [t for t in allt if t["date"] > split]
        last = [t for t in allt if t["date"] >= recent]
        print("== " + name); print(summarize(dev, "  2010-2019")); print(summarize(conf, "  2020-2026")); print(summarize(last, "  last 3 months"))
        for risk in (0.01, 0.02):
            for lab, lo, hi in (("2010-19", dt.date(2010, 6, 1), split), ("2020-26", dt.date(2020, 1, 1), dt.date(2025, 10, 1))):
                starts = [lo + dt.timedelta(days=x) for x in range(0, (hi - lo).days, 15)]
                res = [challenge(allt, s, risk) for s in starts]
                p = [n for o, n in res if o == "pass"]
                print("    challenge 10%% target, risk %d%%/trade %s: pass %4.1f%% fail %4.1f%% (median %s trading days to pass)" % (
                    risk * 100, lab, 100 * len(p) / len(res), 100 * sum(o == "fail" for o, _ in res) / len(res), int(st.median(p)) if p else "-"))
        sys.stdout.flush()
