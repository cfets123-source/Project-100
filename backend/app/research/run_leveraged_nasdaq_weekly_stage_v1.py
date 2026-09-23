"""Milestone screen using ProShares' split-aware daily NAV percentage changes."""
from __future__ import annotations

import csv
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys

from app.research.run_crypto_weekly_breakout_stage_v2 import _resampled_hits


TICKERS = ("SQQQ", "TQQQ")
WINDOWS = ((date(2024, 9, 23), date(2025, 9, 19)),
           (date(2025, 9, 22), date(2026, 9, 21)))
ONE_WAY_COST = .0025
SOURCE_URL = "https://accounts.profunds.com/etfdata/historical_nav.csv"


def load_nav(path: Path) -> tuple[list[date], dict[str, dict[date, float]], str]:
    source = path.read_bytes()
    changes = {ticker: {} for ticker in TICKERS}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = row["Ticker"]
            if ticker not in changes:
                continue
            day = datetime.strptime(row["Date"], "%m/%d/%Y").date()
            if not date(2024, 8, 1) <= day <= date(2026, 9, 22):
                continue
            nav = float(row["NAV"])
            prior = float(row["Prior NAV"])
            daily_change = float(row["NAV Change (%)"]) / 100.0
            if nav <= 0 or prior <= 0 or abs(nav / prior - 1 - daily_change) > .00002:
                raise ValueError(f"Inconsistent issuer NAV change for {ticker} {day}")
            changes[ticker][day] = daily_change
    days = sorted(changes[TICKERS[0]])
    if not days or set(days) != set(changes[TICKERS[1]]):
        raise ValueError("TQQQ/SQQQ trading dates do not match")
    for start, end in WINDOWS:
        if start not in days or end not in days:
            raise ValueError(f"Missing a fixed window boundary: {start} to {end}")
        if days.index(start) < 21 or days.index(end) + 1 >= len(days):
            raise ValueError(f"Missing signal warmup or next-close return: {start} to {end}")
    return days, changes, hashlib.sha256(source).hexdigest()


def evaluate(days: list[date], changes: dict[str, dict[date, float]],
             start: date, end: date) -> dict:
    first = days.index(start)
    last = days.index(end)
    current = None
    equity = zero_cost = peak = 100.0
    first500 = first1000 = None
    drawdown = 0.0
    entries = exits = cash_days = 0
    rows = []
    for i in range(first, last + 1):
        day = days[i]
        target = current
        if i == first or day.isocalendar()[:2] != days[i - 1].isocalendar()[:2]:
            candidates = []
            for ticker in TICKERS:
                factor = 1.0
                for j in range(i - 20, i):
                    factor *= 1 + changes[ticker][days[j]]
                momentum = factor - 1
                if momentum > 0:
                    candidates.append((momentum, ticker))
            target = sorted(candidates, key=lambda pair: (-pair[0], pair[1]))[0][1] if candidates else None
        legs = int(current is not None and current != target) + int(target is not None and target != current)
        entries += int(target is not None and target != current)
        exits += int(current is not None and current != target)
        next_day = days[i + 1]
        gross = 1 + changes[target][next_day] if target else 1.0
        net_return = (1 - ONE_WAY_COST) ** legs * gross - 1
        equity *= 1 + net_return
        zero_cost *= gross
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
        first500 = first500 or (day.isoformat() if equity >= 500 else None)
        first1000 = first1000 or (day.isoformat() if equity >= 1000 else None)
        cash_days += target is None
        rows.append({"date": day.isoformat(), "asset": target or "CASH",
                     "net_return": round(net_return, 12), "equity": round(equity, 8)})
        current = target
    return {"start": start.isoformat(), "end": end.isoformat(),
            "trading_days": len(rows), "observed_end": equity, "zero_cost_end": zero_cost,
            "first_500_day": first500, "first_1000_day": first1000,
            "max_drawdown": drawdown, "entries": entries, "exits": exits,
            "cash_days": cash_days,
            "resampled": _resampled_hits([row["net_return"] for row in rows]),
            "daily_account_returns": rows}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m app.research.run_leveraged_nasdaq_weekly_stage_v1 NAV.csv RESULT.json")
    days, changes, file_hash = load_nav(Path(sys.argv[1]))
    result = {"rule": "leveraged_nasdaq_weekly_stage_v1", "tickers": TICKERS,
              "source": SOURCE_URL, "source_sha256": file_hash,
              "one_way_cost": ONE_WAY_COST,
              "source_daily_changes": {ticker: [[day.isoformat(), changes[ticker][day]] for day in days]
                                       for ticker in TICKERS},
              "windows": [evaluate(days, changes, start, end) for start, end in WINDOWS]}
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")
    for window in result["windows"]:
        print(json.dumps({key: value for key, value in window.items()
                          if key != "daily_account_returns"}, indent=2))


if __name__ == "__main__":
    main()
