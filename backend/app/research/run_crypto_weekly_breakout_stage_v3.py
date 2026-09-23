"""Run the complete-history six-coin version of weekly breakout V2."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from app.research.run_crypto_weekly_breakout_stage_v2 import (
    WINDOWS, ONE_WAY_COST, evaluate_window, get_candles,
)

COINS = ("AVAX", "BONK", "BTC", "DOGE", "ETH", "SOL")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.research.run_crypto_weekly_breakout_stage_v3 RESULT.json")
    data = {coin: get_candles(coin) for coin in COINS}
    source = json.dumps({coin: [[day.isoformat(), *data[coin][day]] for day in sorted(data[coin])]
                         for coin in COINS}, separators=(",", ":"))
    result = {"rule": "crypto_weekly_breakout_stage_v3", "coins": COINS,
              "source": "Coinbase Exchange UTC daily candles",
              "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
              "one_way_cost": ONE_WAY_COST,
              "windows": [evaluate_window(data, start, end, COINS) for start, end in WINDOWS]}
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
    for window in result["windows"]:
        print(json.dumps({key: value for key, value in window.items()
                          if key != "daily_account_returns"}, indent=2))


if __name__ == "__main__":
    main()
