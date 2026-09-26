"""Run the frozen SMC FVG retest v2 study (15-minute bars) on public Coinbase candles.

Usage (from backend/): python -m app.research.run_smc_fvg_retest_v2
See docs/SMC_FVG_RETEST_V2_PLAN.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode

from app.research.run_smc_fvg_retest_v1 import _get
from app.research.smc_fvg_retest_v1 import Candle, SimConfig, simulate_window, summarize
from app.research.stage_distribution import assess_stage_distribution

COINS = ("BTC", "ETH", "SOL")
GRANULARITY = 900
FETCH_START = datetime(2025, 9, 1, tzinfo=timezone.utc)
FETCH_END = datetime(2026, 9, 22, tzinfo=timezone.utc)
WINDOWS = {
    "development": (datetime(2025, 9, 22, tzinfo=timezone.utc), datetime(2025, 12, 22, tzinfo=timezone.utc)),
    "confirmation": (datetime(2025, 12, 22, tzinfo=timezone.utc), datetime(2026, 3, 22, tzinfo=timezone.utc)),
}
SUPPLEMENTARY = {"v1_window_replay": (datetime(2026, 3, 23, tzinfo=timezone.utc), FETCH_END)}
CACHE = Path(__file__).resolve().parents[2] / ".research_cache" / "smc_fvg_retest_v2"
DOCS = Path(__file__).resolve().parents[3] / "docs"
PRIMARY_FEE = 0.0025
SLIPPAGE = 0.0005
MIN_STOP = round(3 * 2 * (PRIMARY_FEE + SLIPPAGE), 6)  # 1.80%, fixed across sensitivities
SENSITIVITY_FEES = (0.0, 0.0010, 0.0075)


def config(fee: float) -> SimConfig:
    return SimConfig(fee_per_leg=fee, slippage=SLIPPAGE, min_stop_pct=MIN_STOP,
                     htf_bucket_seconds=3600, anchor_target_to_fill=True)


def fetch_coin(coin: str) -> list[Candle]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{coin}-USD-15m.json.gz"
    if path.exists():
        rows = json.loads(gzip.decompress(path.read_bytes()))
    else:
        by_ts: dict[int, list] = {}
        start = FETCH_START
        while start < FETCH_END:
            end = min(start + timedelta(seconds=GRANULARITY * 300), FETCH_END)
            q = urlencode({"start": start.isoformat().replace("+00:00", "Z"),
                           "end": end.isoformat().replace("+00:00", "Z"), "granularity": GRANULARITY})
            for row in _get(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles?{q}"):
                if int(start.timestamp()) <= int(row[0]) < int(end.timestamp()):
                    by_ts[int(row[0])] = row
            start = end
            time.sleep(0.11)
        rows = [by_ts[k] for k in sorted(by_ts)]
        path.write_bytes(gzip.compress(json.dumps(rows).encode()))
    return [Candle(ts=int(r[0]), open=float(r[3]), high=float(r[2]), low=float(r[1]),
                   close=float(r[4]), volume=float(r[5])) for r in rows]


def run_windows(series: dict, windows: dict) -> tuple[dict, list[float]]:
    out, daily = {}, []
    for name, (start, end) in windows.items():
        res = {}
        for fee in (PRIMARY_FEE, *SENSITIVITY_FEES):
            sim = simulate_window(series, int(start.timestamp()), int(end.timestamp()), config(fee), COINS)
            res[f"fee_{fee:.4f}"] = summarize(sim)
            if fee == PRIMARY_FEE:
                res["primary_trades"] = sim["trades"]
                daily += sim["daily_returns"]
        out[name] = res
        p = res[f"fee_{PRIMARY_FEE:.4f}"]
        print(f"{name}: end=${p['ending_equity']:.2f} trades={p['trades']} win={p['win_rate']:.1%} "
              f"avgR={p['avg_r']:.2f} PF={p['profit_factor']:.2f} maxDD={p['max_drawdown']:.1%} "
              f"signals={p['n_signals']} skip_stop={p['n_skipped_stop_pct']} skip_drift={p['n_skipped_drift']}",
              flush=True)
    return out, daily


def main() -> int:
    series = {c: fetch_coin(c) for c in COINS}
    expected = int((FETCH_END - FETCH_START).total_seconds() // GRANULARITY)
    h = hashlib.sha256()
    for c in COINS:
        print(f"{c}: {len(series[c])} bars, {expected - len(series[c])} missing", flush=True)
        for b in series[c]:
            h.update(f"{c},{b.ts},{b.open},{b.high},{b.low},{b.close},{b.volume}\n".encode())
    out: dict = {"data_sha256": h.hexdigest(), "min_stop_pct": MIN_STOP,
                 "missing_bars": {c: expected - len(series[c]) for c in COINS}}
    out["windows"], daily = run_windows(series, WINDOWS)
    out["supplementary"], _ = run_windows(series, SUPPLEMENTARY)
    dist = assess_stage_distribution(daily, start_equity=100.0, target_equity=500.0, horizon_days=len(daily),
                                     floor_fraction_of_start=0.5, block_days=5, paths=10000, seed=20260927)
    out["stage_distribution"] = dist.__dict__
    prim = [out["windows"][w][f"fee_{PRIMARY_FEE:.4f}"] for w in WINDOWS]
    out["pass"] = all(p["ending_equity"] > 100 and p["profit_factor"] >= 1.2 and p["trades"] >= 30
                      and p["max_drawdown"] <= 0.35 for p in prim)
    out["combined_daily_returns"] = daily
    (DOCS / "SMC_FVG_RETEST_V2_RESULT.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["stage_distribution"], default=str))
    print("PASS" if out["pass"] else "FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
