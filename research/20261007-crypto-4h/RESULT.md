# 4-hour crypto test — result (7 October 2026): FAIL, keep daily

The adoption rule in PLAN.md was fixed before running. The test used Binance.US BTC/ETH/SOL data from listing to October 2026, cost 0.05% per side, 3 slots, and the same breakout + trend rules.

| Variant | 2020–2022 | 2023–Sep 2026 | Last 12 months |
|---|---|---|---|
| D: daily (live strategy) | $146 (38% worst drop, 110 trades) | **$256 (24%, 76)** | **$109 (11%, 13)** |
| 4A: 4h, same stops | **$237 (50%, 373)** | $101 (54%, 198) | $101 (36%, 80) |
| 4B: 4h, volatility-scaled stops | $121 (38%, 687) | $59 (57%, 484) | $80 (30%, 181) |

Neither 4-hour version beat the daily version in both periods. 4A won only in 2020–2022, the 2021 bull run. 4B lost money overall. Faster bars meant 3–6× more trades, larger drops, and more whipsaws against noise. The stress test was not needed, because both variants failed the first condition. Decision: the live Binance worker stays on daily bars.
