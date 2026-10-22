"""NOISE intraday momentum signal (Zarattini, Aziz & Barbon 2024), identical to the rules tested in
research/20261013-intraday and research/20261021-prop-challenge, applied to the traded futures contract.

Bars: 5-minute, keyed by ET start time, regular session 9:30-15:55 only.
Checks: bars that close on the hour from 10:00 to 15:00 (bar starts 9:55 ... 14:55); 30-min checks if HOURLY=False.
"""
import datetime as dt

OPEN = dt.time(9, 30)
LAST = dt.time(15, 55)
LOOKBACK = 14


HOURLY = True  # 2026-10-22 ladder research: hourly checks beat 30-min checks on 2019-2023 and on unseen 2024-2026


def is_check(t):
    minutes = (55,) if HOURLY else (25, 55)
    return t.minute in minutes and dt.time(9, 55) <= t <= dt.time(15, 25)


def sigma(history, t):
    """history: list of previous days, each {time: (o,h,l,c,v)}. Average |close(t)/open - 1| over the last 14."""
    vals = []
    for day in history[-LOOKBACK:]:
        if OPEN in day and t in day:
            vals.append(abs(day[t][3] / day[OPEN][0] - 1))
    return sum(vals) / len(vals) if len(vals) >= 10 else None


def vwap(today, upto):
    pv = vol = 0.0
    last = None
    for t in sorted(today):
        if t > upto:
            break
        o, h, l, c, v = today[t]
        pv += (h + l + c) / 3 * v
        vol += v
        last = c
    return pv / vol if vol else last


def decide(history, today, t, position):
    """Decision after the bar starting at t closes. position: +1 long, -1 short, 0 flat.
    Returns the target position (+1, -1, 0) or None when no check applies."""
    if not is_check(t) or t not in today or OPEN not in today or not history:
        return None
    prev_close = history[-1].get(LAST, (None, None, None, None))[3]
    s = sigma(history, t)
    if prev_close is None or s is None:
        return None
    op = today[OPEN][0]
    c = today[t][3]
    up = max(op, prev_close) * (1 + s)
    dn = min(op, prev_close) * (1 - s)
    vw = vwap(today, t)
    target = position
    if position > 0 and c < max(up, vw):
        target = 0
    elif position < 0 and c > min(dn, vw):
        target = 0
    if target == 0:
        target = 1 if c > up else -1 if c < dn else 0
    return target


VOL_TARGET = 0.010  # daily volatility target for position sizing (research/20261022-ladder)


def vol_scale(history, target=VOL_TARGET, lo=0.5, hi=2.0):
    """Size multiplier = target / recent daily volatility (14 close-to-close returns), clamped to [lo, hi]."""
    closes = [d[LAST][3] for d in history if LAST in d][-15:]
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    if len(rets) < 5:
        return 1.0
    m = sum(rets) / len(rets)
    vol = (sum((r - m) ** 2 for r in rets) / len(rets)) ** 0.5
    return max(lo, min(hi, target / vol)) if vol > 0 else hi
