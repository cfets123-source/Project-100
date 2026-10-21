"""NOISE intraday momentum signal (Zarattini, Aziz & Barbon 2024), identical to the rules tested in
research/20261013-intraday and research/20261021-prop-challenge, applied to the traded futures contract.

Bars: 5-minute, keyed by ET start time, regular session 9:30-15:55 only.
Checks: bars that close at :00 / :30 from 10:00 to 15:30 (bar starts 9:55 ... 15:25).
"""
import datetime as dt

OPEN = dt.time(9, 30)
LAST = dt.time(15, 55)
LOOKBACK = 14


def is_check(t):
    return t.minute in (25, 55) and dt.time(9, 55) <= t <= dt.time(15, 25)


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
