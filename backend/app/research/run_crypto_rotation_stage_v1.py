"""Reproduce a fixed crypto rotation research path from Coinbase public candles."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.research.stage_distribution import assess_stage_distribution


COINS = ("BTC", "DOGE", "ETH", "SOL")
FIRST_DATA_DAY = date(2025, 8, 15)
FIRST_TEST_DAY = date(2025, 9, 22)
LAST_TEST_DAY = date(2026, 9, 21)
LAST_OPEN_DAY = LAST_TEST_DAY + timedelta(days=1)
ONE_WAY_COST = 0.0075


def _utc(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def load_candles(coin: str) -> dict[date, tuple[float, float]]:
    candles: dict[date, tuple[float, float]] = {}
    start = FIRST_DATA_DAY
    while start <= LAST_OPEN_DAY:
        end = min(start + timedelta(days=200), LAST_OPEN_DAY + timedelta(days=1))
        query = urlencode({"start": datetime.fromtimestamp(_utc(start), timezone.utc).isoformat(),
                           "end": datetime.fromtimestamp(_utc(end), timezone.utc).isoformat(),
                           "granularity": 86400})
        url = f"https://api.exchange.coinbase.com/products/{coin}-USD/candles?{query}"
        req = Request(url, headers={"User-Agent": "Project100-research/1.0"})
        for attempt in range(4):
            try:
                with urlopen(req, timeout=25) as response:
                    rows = json.load(response)
                if not isinstance(rows, list):
                    raise ValueError(f"Unexpected {coin} response: {rows}")
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        for row in rows:
            day = datetime.fromtimestamp(row[0], timezone.utc).date()
            if start <= day < end:
                opening, closing = float(row[3]), float(row[4])
                if opening <= 0 or closing <= 0:
                    raise ValueError(f"Invalid {coin} candle on {day}")
                candles[day] = opening, closing
        start = end
        time.sleep(0.12)
    required = [FIRST_DATA_DAY + timedelta(days=i)
                for i in range((LAST_OPEN_DAY - FIRST_DATA_DAY).days + 1)]
    missing = [day.isoformat() for day in required if day not in candles]
    if missing:
        raise ValueError(f"{coin} missing {len(missing)} daily candles: {missing[:5]}")
    return candles


def evaluate(data: dict[str, dict[date, tuple[float, float]]]) -> dict:
    daily = []
    holdings = []
    equity = 100.0
    current = None
    entries = exits = 0
    for offset in range((LAST_TEST_DAY - FIRST_TEST_DAY).days + 1):
        day = FIRST_TEST_DAY + timedelta(days=offset)
        signal_day = day - timedelta(days=1)
        candidates = []
        for coin in COINS:
            series = data[coin]
            close = series[signal_day][1]
            past_close = series[signal_day - timedelta(days=14)][1]
            mean30 = sum(series[signal_day - timedelta(days=i)][1]
                         for i in range(30)) / 30
            momentum = close / past_close - 1
            if momentum > 0 and close > mean30:
                candidates.append((momentum, coin))
        target = sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1] if candidates else None
        legs = int(current is not None and current != target) + int(target is not None and target != current)
        entries += int(target is not None and target != current)
        exits += int(current is not None and current != target)
        next_day = day + timedelta(days=1)
        gross_factor = (data[target][next_day][0] / data[target][day][0]) if target else 1.0
        net_return = (1.0 - ONE_WAY_COST) ** legs * gross_factor - 1.0
        equity *= 1 + net_return
        daily.append({"date": day.isoformat(), "asset": target or "CASH",
                      "net_return": round(net_return, 12), "equity": round(equity, 8)})
        holdings.append(target or "CASH")
        current = target
    returns = [day["net_return"] for day in daily]
    distribution = assess_stage_distribution(
        returns, start_equity=100, target_equity=1000, horizon_days=365,
        floor_fraction_of_start=.5, block_days=5, paths=10000, seed=20260923)
    raw = json.dumps({coin: [[day.isoformat(), *data[coin][day]] for day in sorted(data[coin])]
                      for coin in COINS}, separators=(",", ":"))
    return {"rule": "crypto_rotation_stage_v1", "first_day": FIRST_TEST_DAY.isoformat(),
            "last_day": LAST_TEST_DAY.isoformat(), "source": "Coinbase Exchange UTC daily candles",
            "source_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "one_way_cost": ONE_WAY_COST, "entries": entries, "exits": exits,
            "cash_days": holdings.count("CASH"), "asset_days": {coin: holdings.count(coin) for coin in COINS},
            "stage_distribution": asdict(distribution), "daily_account_returns": daily}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.research.run_crypto_rotation_stage_v1 RESULT.json")
    data = {coin: load_candles(coin) for coin in COINS}
    result = evaluate(data)
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "daily_account_returns"}, indent=2))


if __name__ == "__main__":
    main()
