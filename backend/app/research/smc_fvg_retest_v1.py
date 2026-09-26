"""SMC fair-value-gap retest v1 — frozen research implementation.

Exact port of the Apex `signal_engine.find_setup` bullish path (see
docs/SMC_FVG_RETEST_V1_PLAN.md), vectorised with precomputed pivots so a year of
1-minute bars can be replayed. Long-only spot crypto; one position across coins.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import math


@dataclass(frozen=True)
class Candle:
    ts: int  # bar start, unix seconds UTC
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class SimConfig:
    fee_per_leg: float = 0.0025
    slippage: float = 0.0005
    risk_pct: float = 0.02
    max_notional_pct: float = 0.95
    min_notional: float = 1.0
    min_rr: float = 3.0
    max_rr: float = 8.0
    min_stop_pct: float = 0.003
    daily_dd: float = 0.05
    halt_seconds: int = 86400
    start_equity: float = 100.0
    # signal parameters (frozen)
    k: int = 2
    window: int = 240
    expiry: int = 30
    min_fvg_atr: float = 0.10
    htf_buckets: int = 120
    htf_min: int = 20
    min_bars: int = 60
    htf_required: bool = True  # test hook only; the frozen study keeps True
    htf_bucket_seconds: int = 300  # v1: 5-minute buckets over 1-minute bars
    anchor_target_to_fill: bool = False  # v2: re-anchor the signal's R multiple at the fill
    target_equity: float = 500.0


@dataclass(frozen=True)
class Signal:
    index: int
    ts: int
    close: float
    stop: float
    target: float
    fvg_top: float
    fvg_bottom: float


# ----------------------------------------------------------------------------- structure helpers
def _pivots(highs: list[float], lows: list[float], k: int) -> tuple[list[int], list[int]]:
    ph, pl = [], []
    n = len(highs)
    for i in range(k, n - k):
        h, l = highs[i], lows[i]
        if all(h > highs[j] for j in range(i - k, i)) and all(h >= highs[j] for j in range(i + 1, i + k + 1)):
            ph.append(i)
        if all(l < lows[j] for j in range(i - k, i)) and all(l <= lows[j] for j in range(i + 1, i + k + 1)):
            pl.append(i)
    return ph, pl


def structure_bias(highs: list[float], lows: list[float], closes: list[float], k: int) -> int:
    """+1 bullish / -1 bearish / 0 none — identical to Apex structure_bias."""
    ph, pl = _pivots(highs, lows, k)
    bias, hp, lp = 0, 0, 0
    last_hi = last_lo = None
    for t in range(len(closes)):
        while hp < len(ph) and ph[hp] + k <= t:
            last_hi = highs[ph[hp]]
            hp += 1
        while lp < len(pl) and pl[lp] + k <= t:
            last_lo = lows[pl[lp]]
            lp += 1
        c = closes[t]
        if last_hi is not None and c > last_hi:
            bias, last_hi = 1, None
        elif last_lo is not None and c < last_lo:
            bias, last_lo = -1, None
    return bias


def _htf_bias_by_minute(candles: list[Candle], cfg: SimConfig) -> list[int]:
    """Bias from the last `htf_buckets` COMPLETED 5-minute buckets for every 1-minute bar."""
    buckets: list[list[float]] = []  # [bucket_id, high, low, close]
    bucket_pos: list[int] = []  # for each minute: index of its bucket in `buckets`
    for c in candles:
        b = c.ts // cfg.htf_bucket_seconds
        if not buckets or buckets[-1][0] != b:
            buckets.append([b, c.high, c.low, c.close])
        else:
            cur = buckets[-1]
            cur[1], cur[2], cur[3] = max(cur[1], c.high), min(cur[2], c.low), c.close
        bucket_pos.append(len(buckets) - 1)
    bias_after: list[int] = []
    for b in range(len(buckets)):
        lo = max(0, b - cfg.htf_buckets + 1)
        seg = buckets[lo:b + 1]
        bias_after.append(structure_bias([x[1] for x in seg], [x[2] for x in seg], [x[3] for x in seg], cfg.k))
    out = []
    for pos in bucket_pos:
        completed = pos  # buckets strictly before the current one
        out.append(bias_after[pos - 1] if completed >= cfg.htf_min else 0)
    return out


# ----------------------------------------------------------------------------- signals
def compute_signals(candles: list[Candle], cfg: SimConfig) -> dict[int, Signal]:
    n = len(candles)
    H = [c.high for c in candles]
    L = [c.low for c in candles]
    C = [c.close for c in candles]
    k = cfg.k
    ph, pl = _pivots(H, L, k)
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    htf = _htf_bias_by_minute(candles, cfg)
    consumed: set[int] = set()
    out: dict[int, Signal] = {}

    def last_pivot(piv: list[int], lo: int, hi: int) -> int | None:
        if hi < lo:
            return None
        idx = bisect_right(piv, hi) - 1
        return piv[idx] if idx >= 0 and piv[idx] >= lo else None

    for t in range(cfg.min_bars - 1, n):
        w = max(0, t - cfg.window + 1)
        a = sum(tr[t - 13:t + 1]) / 14 if t - 13 >= max(w + 1, 1) else 0.0
        # 1) sweep
        sweep = lvl = None
        for s in range(t - 1, max(t - cfg.expiry, w) - 1, -1):
            j = last_pivot(pl, w + k, s - k)
            if j is None:
                continue
            if L[s] < L[j] and C[s] > L[j]:
                sweep, lvl = s, L[j]
                break
        if sweep is None:
            continue
        # 2) MSS
        jh = last_pivot(ph, w + k, sweep - k)
        if jh is None:
            continue
        mss_level = H[jh]
        mss = next((m for m in range(sweep + 1, t) if C[m] > mss_level), None)
        if mss is None:
            continue
        # 3) latest bullish FVG in displacement leg
        min_size = a * cfg.min_fvg_atr
        fvg_c = None
        for c3 in range(min(mss + 1, t - 1), sweep + 1, -1):
            if c3 - 2 >= sweep and H[c3 - 2] < L[c3] and (L[c3] - H[c3 - 2]) >= min_size:
                fvg_c = c3
                break
        if fvg_c is None:
            continue
        top, bottom = L[fvg_c], H[fvg_c - 2]
        # 4) first retest on bar t
        if any(L[b] <= top for b in range(fvg_c + 1, t)):
            continue
        if not (L[t] <= top and C[t] > bottom):
            continue
        # 5) levels
        stop = L[sweep] - 0.1 * a
        entry = C[t]
        risk = entry - stop
        if risk <= 0:
            continue
        above = [H[j] for j in ph[bisect_right(ph, w + k - 1):bisect_right(ph, t - k)] if H[j] > entry]
        target = entry + cfg.min_rr * risk
        if above:
            rr_liq = (min(above) - entry) / risk
            if rr_liq >= cfg.min_rr:
                target = entry + min(rr_liq, cfg.max_rr) * risk
        key = candles[fvg_c].ts
        if key in consumed:
            continue
        consumed.add(key)
        if cfg.htf_required and htf[t] != 1:
            continue
        out[t] = Signal(index=t, ts=candles[t].ts, close=entry, stop=stop, target=target,
                        fvg_top=top, fvg_bottom=bottom)
    return out


_SIGNAL_CACHE: dict[tuple, dict[int, Signal]] = {}


def signals_for(coin: str, candles: list[Candle], cfg: SimConfig) -> dict[int, Signal]:
    key = (coin, len(candles), candles[0].ts if candles else 0, cfg.htf_bucket_seconds, cfg.k, cfg.window, cfg.expiry,
           cfg.min_fvg_atr, cfg.htf_buckets, cfg.htf_min, cfg.min_rr, cfg.max_rr)
    if key not in _SIGNAL_CACHE:
        _SIGNAL_CACHE[key] = compute_signals(candles, cfg)
    return _SIGNAL_CACHE[key]


# ----------------------------------------------------------------------------- simulation
@dataclass
class _Pos:
    coin: str
    qty: float
    entry: float
    stop: float
    target: float
    entry_ts: int
    risk_usd: float
    entry_fee: float


def simulate_window(series: dict[str, list[Candle]], start: int, end: int, cfg: SimConfig,
                    coin_order: tuple[str, ...]) -> dict:
    idx = {c: {bar.ts: i for i, bar in enumerate(series[c])} for c in coin_order}
    sigs = {c: signals_for(c, series[c], cfg) for c in coin_order}
    timeline = sorted({bar.ts for c in coin_order for bar in series[c] if start <= bar.ts < end})
    cash = cfg.start_equity
    pos: _Pos | None = None
    pending: tuple[str, int, Signal] | None = None  # coin, bar index to enter on, signal
    halted_until = -1
    last_close: dict[str, float] = {}
    trades: list[dict] = []
    stats = {"signals": 0, "skipped_busy": 0, "skipped_halt": 0, "skipped_drift": 0,
             "skipped_stop_pct": 0, "skipped_size": 0, "breaker_trips": 0}
    peak = cash
    max_dd = 0.0
    reached_ts = None
    day = start // 86400
    day_start_eq = cash
    day_prev_eq = cash
    daily: list[float] = []
    marked = cash

    def close_pos(px: float, ts: int, reason: str) -> None:
        nonlocal cash, pos
        fee = pos.qty * px * cfg.fee_per_leg
        cash += pos.qty * px - fee
        pnl = (px - pos.entry) * pos.qty - fee - pos.entry_fee
        trades.append({"coin": pos.coin, "entry_ts": pos.entry_ts, "exit_ts": ts, "entry": pos.entry,
                       "exit": px, "stop": pos.stop, "target": pos.target, "qty": pos.qty,
                       "pnl": pnl, "r": pnl / pos.risk_usd if pos.risk_usd else 0.0, "reason": reason})
        pos = None

    for ts in timeline:
        d = ts // 86400
        while d > day:  # UTC day roll: record the completed day's net return
            daily.append(marked / day_prev_eq - 1.0)
            day_prev_eq = marked
            day_start_eq = marked
            day += 1

        # 1) pending entry at this bar's open
        if pending is not None:
            coin, bi, sig = pending
            bars = series[coin]
            if bi < len(bars) and bars[bi].ts == ts:
                pending = None
                fill = bars[bi].open * (1 + cfg.slippage)
                risk_u = fill - sig.stop
                target = sig.target
                if cfg.anchor_target_to_fill and risk_u > 0:
                    multiple = (sig.target - sig.close) / (sig.close - sig.stop)
                    target = fill + multiple * risk_u
                if fill <= sig.stop or fill >= target or risk_u <= 0 or (target - fill) / risk_u < cfg.min_rr - 1e-9:
                    stats["skipped_drift"] += 1
                elif risk_u / fill < cfg.min_stop_pct:
                    stats["skipped_stop_pct"] += 1
                else:
                    eq = cash
                    qty = min(cfg.risk_pct * eq / risk_u, cfg.max_notional_pct * eq / fill)
                    qty = math.floor(qty * 1e8) / 1e8
                    if qty * fill < cfg.min_notional:
                        stats["skipped_size"] += 1
                    else:
                        fee = qty * fill * cfg.fee_per_leg
                        cash -= qty * fill + fee
                        pos = _Pos(coin, qty, fill, sig.stop, target, ts, qty * risk_u, fee)
            elif bi >= len(bars) or bars[bi].ts < ts:
                pending = None

        # 2) exits on the position coin's bar
        if pos is not None and ts in idx[pos.coin]:
            b = series[pos.coin][idx[pos.coin][ts]]
            if b.low <= pos.stop:
                px = (b.open if b.open < pos.stop else pos.stop) * (1 - cfg.slippage)
                close_pos(px, ts, "stop")
            elif b.high >= pos.target:
                close_pos(pos.target * (1 - cfg.slippage), ts, "target")

        for c in coin_order:
            if ts in idx[c]:
                last_close[c] = series[c][idx[c][ts]].close

        # 3) mark, drawdown, breaker
        marked = cash + (pos.qty * last_close.get(pos.coin, pos.entry) if pos else 0.0)
        if marked <= day_start_eq * (1 - cfg.daily_dd) and ts >= halted_until:
            stats["breaker_trips"] += 1
            if pos is not None:
                close_pos(last_close[pos.coin] * (1 - cfg.slippage), ts, "circuit_breaker")
            marked = cash
            halted_until = ts + cfg.halt_seconds
        peak = max(peak, marked)
        max_dd = max(max_dd, 1 - marked / peak if peak > 0 else 0.0)
        if reached_ts is None and marked >= cfg.target_equity:
            reached_ts = ts

        # 4) new signals at this bar's close
        for c in coin_order:
            i = idx[c].get(ts)
            if i is None or i not in sigs[c]:
                continue
            stats["signals"] += 1
            if pos is not None or pending is not None:
                stats["skipped_busy"] += 1
            elif ts < halted_until:
                stats["skipped_halt"] += 1
            else:
                pending = (c, i + 1, sigs[c][i])

    if pos is not None:
        close_pos(last_close[pos.coin] * (1 - cfg.slippage), end, "window_end")
        marked = cash
    last_day = (end - 1) // 86400
    while day <= last_day:
        daily.append(marked / day_prev_eq - 1.0)
        day_prev_eq = marked
        day += 1
    return {"ending_equity": cash, "trades": trades, "stats": stats, "max_drawdown": max_dd,
            "reached_500_ts": reached_ts, "daily_returns": daily}


def summarize(sim: dict, target: float = 500.0) -> dict:
    tr = sim["trades"]
    wins = [t["pnl"] for t in tr if t["pnl"] > 0]
    losses = [t["pnl"] for t in tr if t["pnl"] <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (99.0 if wins else 0.0)
    return {
        "ending_equity": round(sim["ending_equity"], 4),
        "net_return": round(sim["ending_equity"] / 100.0 - 1, 4),
        "trades": len(tr),
        "win_rate": (len(wins) / len(tr)) if tr else 0.0,
        "avg_r": (sum(t["r"] for t in tr) / len(tr)) if tr else 0.0,
        "profit_factor": round(pf, 3),
        "max_drawdown": round(sim["max_drawdown"], 4),
        "reached_target": sim["reached_500_ts"] is not None,
        "exit_reasons": {r: sum(1 for t in tr if t["reason"] == r) for r in {t["reason"] for t in tr}},
        "days": len(sim["daily_returns"]),
        **{f"n_{k}": v for k, v in sim["stats"].items()},
    }
