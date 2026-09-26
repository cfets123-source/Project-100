"""Frozen SMC FVG retest v1: signal geometry and conservative simulation rules."""
from app.research.smc_fvg_retest_v1 import Candle, SimConfig, compute_signals, simulate_window, summarize

# Hand-built bullish sequence: swing low 98 swept at bar 10, MSS above 103 at bar 13,
# FVG (bar 11 high 100.5 < bar 13 low 101.5), first retest at bar 17.
OHLC = [(100.2, 101, 100, 100.5), (100.6, 102, 100.5, 101.5), (101.5, 103, 101, 102), (102, 102.5, 100.5, 101),
        (101, 101.5, 99.5, 100), (100, 100.5, 99, 99.5), (99.5, 100, 98, 98.5), (98.6, 99.5, 98.5, 99),
        (99, 100, 99, 99.5), (99.5, 100.2, 99.2, 99.6), (99.6, 99.8, 97.5, 98.6),
        (98.7, 100.5, 98.8, 100.3), (100.4, 102.5, 100.4, 102.3), (102.3, 104.5, 101.5, 104.2),
        (104.2, 104.8, 102.4, 103.8), (103.8, 104, 102.8, 103.2), (103.2, 103.6, 102.2, 102.6),
        (102.6, 102.7, 101.3, 101.9)]
T0 = 1_780_000_000 - 1_780_000_000 % 300


def _candles(rows):
    return [Candle(T0 + 60 * i, o, h, l, c, 1.0) for i, (o, h, l, c) in enumerate(rows)]


def test_retest_signal_geometry():
    sigs = compute_signals(_candles(OHLC), SimConfig(min_bars=10, htf_required=False))
    s = sigs[17]
    assert (s.fvg_bottom, s.fvg_top) == (100.5, 101.5)
    assert s.close == 101.9 and s.stop < 97.5
    assert (s.target - s.close) / (s.close - s.stop) >= 3.0 - 1e-9


def test_signal_enforces_min_rr_and_first_retest():
    cfg = SimConfig(min_bars=10, htf_required=False)
    rows = OHLC + [(101.9, 102.2, 101.2, 101.8)]  # second touch must not signal again
    sigs = compute_signals(_candles(rows), cfg)
    assert 17 in sigs and 18 not in sigs
    for s in sigs.values():
        assert (s.target - s.close) / (s.close - s.stop) >= 3.0 - 1e-9


def _flat_series(n, px=100.0):
    return [Candle(T0 + 60 * i, px, px, px, px, 1.0) for i in range(n)]


def test_simulation_is_flat_without_signals_and_counts_idle_days():
    series = {"BTC": _flat_series(3 * 1440)}
    start = series["BTC"][0].ts
    sim = simulate_window(series, start, start + 3 * 86400, SimConfig(), ("BTC",))
    s = summarize(sim)
    assert s["trades"] == 0 and s["ending_equity"] == 100.0
    assert len(sim["daily_returns"]) >= 3 and all(r == 0 for r in sim["daily_returns"])


def test_v2_anchor_moves_target_with_fill_and_keeps_multiple():
    """v2: a higher fill keeps the signal's R multiple instead of being rejected as drift."""
    rows = OHLC + [(102.4, 104.0, 102.3, 103.0)]  # next open 0.5 above signal close
    candles = _candles(rows)
    series = {"BTC": candles}
    base = dict(min_bars=10, htf_required=False, min_stop_pct=0.0, daily_dd=0.99)
    start, end = candles[0].ts, candles[-1].ts + 60
    v1 = simulate_window(series, start, end, SimConfig(**base), ("BTC",))
    v2 = simulate_window(series, start, end, SimConfig(**base, anchor_target_to_fill=True), ("BTC",))
    assert v1["stats"]["skipped_drift"] == 1 and not v1["trades"]
    t = v2["trades"][0]
    assert abs((t["target"] - t["entry"]) / (t["entry"] - t["stop"]) - 3.0) < 1e-9
