"""Intraday prop-challenge simulator (append to intraday_bt.py; run with the 5-min data dir).
NOISE signal on QQQ, traded as micro Nasdaq futures (long AND short, unleveraged QQQ moves x notional).
Flat every day by 15:55 ET (Topstep-style 3:10 PM CT rule). Rules: $50K, target +$3,000, trailing $2,000 (EOD
high-water, locks at $50K, breach checked on intraday worst), daily loss $1,000 stops that day.
"""
FUT_COST = 0.0001  # per side, fraction of notional (~$1.50 commission + 1 tick on a ~$55K micro contract)

def noise_days(sim):
    sig = sim.noise_sigma()
    out, prev_close = {}, None
    for d in sim.days:
        q = sim.Q[d]
        if d not in sig or prev_close is None:
            prev_close = q[LAST][3]
            continue
        op = q[dt.time(9, 30)][0]
        times = sorted(q)
        pv = vol = 0.0
        vwap = {}
        for t in times:
            o, h, l, c, v = q[t]
            pv += (h + l + c) / 3 * v; vol += v
            vwap[t] = pv / vol if vol else c
        pos, entry, pnl, worst = 0, None, 0.0, 0.0
        for t in times:
            o, h, l, c, v = q[t]
            if pos:
                adverse = (l / entry - 1) if pos > 0 else (1 - h / entry)
                worst = min(worst, pnl + adverse)
            if t.minute in (25, 55) and dt.time(9, 55) <= t <= dt.time(15, 25) and t in sig[d]:
                s = sig[d][t]
                up = max(op, prev_close) * (1 + s); dn = min(op, prev_close) * (1 - s)
                nxt = dt.time(*divmod(tkey(t) + 5, 60))
                if nxt in q:
                    px = q[nxt][0]
                    if pos > 0 and c < max(up, vwap[t]) or pos < 0 and c > min(dn, vwap[t]):
                        pnl += pos * (px / entry - 1) - FUT_COST; pos = 0
                    if pos == 0:
                        want = 1 if c > up else -1 if c < dn else 0
                        if want:
                            pos, entry = want, px; pnl -= FUT_COST
            if t == LAST and pos:
                pnl += pos * (c / entry - 1) - FUT_COST; pos = 0
        out[d] = (pnl, min(worst, pnl))
        prev_close = q[LAST][3]
    return out

def challenge(days, keys, start, size, mode, maxd):
    bal = hw = 50000.0; lock = False; floor = 48000.0; paid = 0.0; n = 0
    for d in keys[start:start + maxd]:
        pnl, worst = days[d]
        notional = 50000 * size
        dayworst = max(worst * notional, -1000.0) if worst * notional < -1000 else worst * notional
        if bal + worst * notional <= floor:
            return ('fail', n, paid)
        daypnl = max(pnl * notional, -1000.0)
        bal += daypnl; n += 1; hw = max(hw, bal)
        if mode == 'eval':
            if bal >= 53000: return ('pass', n, 0)
            if not lock:
                floor = min(50000.0, hw - 2000); lock = floor >= 50000
        else:
            if not lock:
                floor = max(48000.0, hw - 2000)
                if hw - 2000 >= 50000: lock = True; floor = 50000.0
            if lock and bal >= 52000:
                paid += 1800; bal -= 2000; hw = bal
    return ('timeout', n, paid)

def run_challenges(data_dir):
    import statistics as st
    Q, T, S = (load(f"{data_dir}/{s}_5m.csv.gz") for s in ("QQQ", "TQQQ", "SQQQ"))
    sim = Sim(Q, T, S)
    days = noise_days(sim); keys = sorted(days)
    print(f"NOISE futures days={len(keys)} {keys[0]}..{keys[-1]}  avg day {st.mean(p for p,_ in days.values()):.5f}")
    print(f"{'size':>4} {'pass%':>6} {'medDays':>7} {'cost/pass':>9} {'funded payout':>13} {'net/attempt':>11}")
    for size in (1, 2, 3, 4):
        starts = range(0, len(keys) - 300, 2)
        res = [challenge(days, keys, s, size, 'eval', 90) for s in starts]
        p = [r for r in res if r[0] == 'pass']; rate = len(p) / len(res)
        med = st.median([r[1] for r in p]) if p else 0
        months = st.mean([1 + (r[1] > 21) + (r[1] > 42) + (r[1] > 63) for r in res])
        pays = [challenge(days, keys, s + r[1], size, 'funded', 250)[2] for s, r in zip(starts, res) if r[0] == 'pass']
        avgpay = st.mean(pays) if pays else 0
        cost = 49 * months / rate if rate else float('inf')
        print(f"{size:>4} {rate:6.1%} {med:7.0f} {cost:9.0f} {avgpay:13.0f} {rate*avgpay - 49*months:11.0f}")

run_challenges(sys.argv[1] if len(sys.argv) > 1 else "/data/research/intraday")
