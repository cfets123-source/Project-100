"""Fixed weekly crypto breakout milestone study using public Coinbase candles."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


COINS = ("AVAX", "BONK", "BTC", "DOGE", "ETH", "PEPE", "SOL", "WIF")
FIRST_DATA_DAY = date(2024, 8, 20)
LAST_OPEN_DAY = date(2026, 9, 22)
WINDOWS = ((date(2024, 9, 22), date(2025, 9, 21)),
           (date(2025, 9, 22), date(2026, 9, 21)))
ONE_WAY_COST = .0075


def get_candles(coin: str) -> dict[date, tuple[float, float]]:
    candles = {}
    start = FIRST_DATA_DAY
    while start <= LAST_OPEN_DAY:
        end = min(start + timedelta(days=190), LAST_OPEN_DAY + timedelta(days=1))
        query = urlencode({"start": start.isoformat() + "T00:00:00Z",
                           "end": end.isoformat() + "T00:00:00Z", "granularity": 86400})
        request = Request(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles?{query}",
                          headers={"User-Agent": "Project100-research/1.0"})
        for attempt in range(4):
            try:
                with urlopen(request, timeout=25) as response:
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
        time.sleep(.12)
    expected = [FIRST_DATA_DAY + timedelta(days=i)
                for i in range((LAST_OPEN_DAY - FIRST_DATA_DAY).days + 1)]
    missing = [day.isoformat() for day in expected if day not in candles]
    if missing:
        raise ValueError(f"{coin}: {len(missing)} missing daily candles; first: {missing[:5]}")
    return candles


def _resampled_hits(returns: list[float], *, paths: int = 10000) -> dict:
    import random
    rng = random.Random(20260923)
    hits500 = hits1000 = floors = 0
    ends = []
    for _ in range(paths):
        equity = 100.0
        touched500 = touched1000 = touched_floor = False
        sequence = []
        while len(sequence) < len(returns):
            first = rng.randrange(len(returns))
            sequence.extend(returns[(first + j) % len(returns)] for j in range(5))
        for value in sequence[:len(returns)]:
            equity *= 1 + value
            touched500 |= equity >= 500
            touched1000 |= equity >= 1000
            touched_floor |= equity <= 50
        hits500 += touched500
        hits1000 += touched1000
        floors += touched_floor
        ends.append(equity)
    ends.sort()
    return {"paths": paths, "hit_500_fraction": hits500 / paths,
            "hit_1000_fraction": hits1000 / paths, "crossed_50_fraction": floors / paths,
            "ending_equity_p10": ends[int((paths - 1) * .1)],
            "ending_equity_p50": ends[int((paths - 1) * .5)],
            "ending_equity_p90": ends[int((paths - 1) * .9)]}


def evaluate_window(data: dict, start: date, end: date, coins: tuple[str, ...] = COINS) -> dict:
    current = None
    equity = zero_cost_equity = peak = 100.0
    first500 = first1000 = None
    worst_drawdown = 0.0
    entries = exits = cash_days = 0
    daily = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        target = current
        if day.weekday() == 0:
            signal_day = day - timedelta(days=1)
            candidates = []
            for coin in coins:
                closes = data[coin]
                ret = closes[signal_day][1] / closes[signal_day - timedelta(days=28)][1] - 1
                if ret > 0:
                    candidates.append((ret, coin))
            target = sorted(candidates, key=lambda pair: (-pair[0], pair[1]))[0][1] if candidates else None
        legs = int(current is not None and current != target) + int(target is not None and target != current)
        entries += int(target is not None and target != current)
        exits += int(current is not None and current != target)
        next_day = day + timedelta(days=1)
        gross = data[target][next_day][0] / data[target][day][0] if target else 1.0
        net_return = (1 - ONE_WAY_COST) ** legs * gross - 1
        equity *= 1 + net_return
        zero_cost_equity *= gross
        peak = max(peak, equity)
        worst_drawdown = max(worst_drawdown, 1 - equity / peak)
        first500 = first500 or (day.isoformat() if equity >= 500 else None)
        first1000 = first1000 or (day.isoformat() if equity >= 1000 else None)
        cash_days += target is None
        daily.append({"date": day.isoformat(), "asset": target or "CASH",
                      "net_return": round(net_return, 12), "equity": round(equity, 8)})
        current = target
    return {"start": start.isoformat(), "end": end.isoformat(),
            "observed_end": equity, "zero_cost_end": zero_cost_equity,
            "first_500_day": first500, "first_1000_day": first1000,
            "max_drawdown": worst_drawdown, "entries": entries, "exits": exits,
            "cash_days": cash_days, "resampled": _resampled_hits([row["net_return"] for row in daily]),
            "daily_account_returns": daily}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.research.run_crypto_weekly_breakout_stage_v2 RESULT.json")
    data = {coin: get_candles(coin) for coin in COINS}
    source = json.dumps({coin: [[day.isoformat(), *data[coin][day]] for day in sorted(data[coin])]
                         for coin in COINS}, separators=(",", ":"))
    result = {"rule": "crypto_weekly_breakout_stage_v2", "coins": COINS,
              "source": "Coinbase Exchange UTC daily candles",
              "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
              "one_way_cost": ONE_WAY_COST,
              "windows": [evaluate_window(data, start, end) for start, end in WINDOWS]}
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
    for window in result["windows"]:
        print(json.dumps({key: value for key, value in window.items()
                          if key != "daily_account_returns"}, indent=2))


if __name__ == "__main__":
    main()
