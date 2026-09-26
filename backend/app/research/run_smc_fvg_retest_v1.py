"""Run the frozen SMC FVG retest v1 study on public Coinbase 1-minute candles.

Usage (from backend/):
    python -m app.research.run_smc_fvg_retest_v1 --fetch-only
    python -m app.research.run_smc_fvg_retest_v1
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.research.smc_fvg_retest_v1 import (
    Candle, SimConfig, simulate_window, summarize,
)
from app.research.stage_distribution import assess_stage_distribution

COINS = ("BTC", "ETH", "SOL")
WARMUP_START = datetime(2026, 3, 22, tzinfo=timezone.utc)
WINDOWS = {
    "development": (datetime(2026, 3, 23, tzinfo=timezone.utc), datetime(2026, 6, 22, tzinfo=timezone.utc)),
    "confirmation": (datetime(2026, 6, 22, tzinfo=timezone.utc), datetime(2026, 9, 22, tzinfo=timezone.utc)),
}
END = datetime(2026, 9, 22, tzinfo=timezone.utc)
CACHE = Path(__file__).resolve().parents[2] / ".research_cache" / "smc_fvg_retest_v1"
DOCS = Path(__file__).resolve().parents[3] / "docs"
PRIMARY_FEE = 0.0025
SENSITIVITY_FEES = (0.0, 0.0010, 0.0075)


def _get(url: str) -> list:
    req = Request(url, headers={"User-Agent": "Project100-research/1.0"})
    for attempt in range(6):
        try:
            with urlopen(req, timeout=30) as r:
                rows = json.load(r)
            if not isinstance(rows, list):
                raise ValueError(rows)
            return rows
        except Exception:
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)
    return []


def fetch_coin(coin: str) -> list[Candle]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{coin}-USD-1m.json.gz"
    if path.exists():
        rows = json.loads(gzip.decompress(path.read_bytes()))
    else:
        rows_by_ts: dict[int, list] = {}
        start = WARMUP_START
        while start < END:
            end = min(start + timedelta(minutes=300), END)
            q = urlencode({"start": start.isoformat().replace("+00:00", "Z"),
                           "end": end.isoformat().replace("+00:00", "Z"), "granularity": 60})
            for row in _get(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles?{q}"):
                ts = int(row[0])
                if int(start.timestamp()) <= ts < int(end.timestamp()):
                    rows_by_ts[ts] = row
            start = end
            time.sleep(0.11)
        rows = [rows_by_ts[k] for k in sorted(rows_by_ts)]
        path.write_bytes(gzip.compress(json.dumps(rows).encode()))
    # Coinbase row: [time, low, high, open, close, volume]
    return [Candle(ts=int(r[0]), open=float(r[3]), high=float(r[2]), low=float(r[1]),
                   close=float(r[4]), volume=float(r[5])) for r in rows]


def data_hash(series: dict[str, list[Candle]]) -> str:
    h = hashlib.sha256()
    for coin in COINS:
        for c in series[coin]:
            h.update(f"{coin},{c.ts},{c.open},{c.high},{c.low},{c.close},{c.volume}\n".encode())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-only", action="store_true")
    a = ap.parse_args()
    series = {}
    for coin in COINS:
        t0 = time.time()
        series[coin] = fetch_coin(coin)
        expected = int((END - WARMUP_START).total_seconds() // 60)
        print(f"{coin}: {len(series[coin])} candles, {expected - len(series[coin])} missing minutes "
              f"({time.time() - t0:.0f}s)", flush=True)
    if a.fetch_only:
        return 0

    out: dict = {"data_sha256": data_hash(series),
                 "missing_minutes": {c: int((END - WARMUP_START).total_seconds() // 60) - len(series[c]) for c in COINS},
                 "windows": {}}
    combined_daily: list[float] = []
    for name, (start, end) in WINDOWS.items():
        res = {}
        # Signals are fee-independent; each fee level replays the same frozen rule.
        for fee in (PRIMARY_FEE, *SENSITIVITY_FEES):
            sim = simulate_window(series, int(start.timestamp()), int(end.timestamp()),
                                  SimConfig(fee_per_leg=fee), coin_order=COINS)
            res[f"fee_{fee:.4f}"] = summarize(sim, target=500.0)
            if fee == PRIMARY_FEE:
                res["primary_trades"] = sim["trades"]
                combined_daily += sim["daily_returns"]
        out["windows"][name] = res
        p = res[f"fee_{PRIMARY_FEE:.4f}"]
        print(f"{name}: end=${p['ending_equity']:.2f} trades={p['trades']} win={p['win_rate']:.1%} "
              f"PF={p['profit_factor']:.2f} maxDD={p['max_drawdown']:.1%}", flush=True)

    dist = assess_stage_distribution(combined_daily, start_equity=100.0, target_equity=500.0,
                                     horizon_days=len(combined_daily), floor_fraction_of_start=0.5,
                                     block_days=5, paths=10000, seed=20260926)
    out["stage_distribution"] = dist.__dict__
    prim = [out["windows"][w][f"fee_{PRIMARY_FEE:.4f}"] for w in WINDOWS]
    out["pass"] = all(p["ending_equity"] > 100 and p["profit_factor"] >= 1.2 and p["trades"] >= 30
                      and p["max_drawdown"] <= 0.35 for p in prim)
    out["combined_daily_returns"] = combined_daily
    DOCS.mkdir(exist_ok=True)
    (DOCS / "SMC_FVG_RETEST_V1_RESULT.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in ("combined_daily_returns",)}, default=str)[:4000])
    print("PASS" if out["pass"] else "FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
