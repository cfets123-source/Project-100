import datetime as dt
OPEN = dt.time(9, 30); LAST = dt.time(15, 55); LOOKBACK = 14
def is_check(t): return t.minute == 55 and dt.time(9, 55) <= t <= dt.time(15, 25)
def sigma(history, t):
    vals = [abs(d[t][3] / d[OPEN][0] - 1) for d in history[-LOOKBACK:] if OPEN in d and t in d]
    return sum(vals) / len(vals) if len(vals) >= 10 else None
def vwap(today, upto):
    pv = vol = 0.0; last = None
    for t in sorted(today):
        if t > upto: break
        o, h, l, c, v = today[t]; pv += (h + l + c) / 3 * v; vol += v; last = c
    return pv / vol if vol else last
def decide(history, today, t, position):
    if not is_check(t) or t not in today or OPEN not in today or not history: return None
    prev_close = history[-1].get(LAST, (None,) * 4)[3]; s = sigma(history, t)
    if prev_close is None or s is None: return None
    op, c = today[OPEN][0], today[t][3]
    up, dn = max(op, prev_close) * (1 + s), min(op, prev_close) * (1 - s)
    vw = vwap(today, t); target = position
    if position > 0 and c < max(up, vw): target = 0
    elif position < 0 and c > min(dn, vw): target = 0
    if target == 0: target = 1 if c > up else -1 if c < dn else 0
    return target
def vol_scale(history, target=0.010, lo=0.5, hi=2.0):
    closes = [d[LAST][3] for d in history if LAST in d][-15:]
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    if len(rets) < 5: return 1.0
    m = sum(rets) / len(rets); vol = (sum((r - m) ** 2 for r in rets) / len(rets)) ** 0.5
    return max(lo, min(hi, target / vol)) if vol > 0 else hi
