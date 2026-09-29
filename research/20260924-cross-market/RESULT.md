# Cross-market historical screen — September 24, 2026

One of four frozen candidates passed the historical screen: broad US equity trend. It lagged the SPY buy-and-hold benchmark in all three windows and never touched the first $200 milestone. It is a research lead, not a demonstrated aggressive-growth strategy or live approval.

Each window starts independently at $100. Values below are terminal liquidation-equivalent dollars after base modeled costs, with price-only returns. Windows end in 2021, 2024, and September 22, 2026 respectively.

| Candidate | 2018–2021 | 2022–2024 | 2025–2026 | Screen |
|---|---:|---:|---:|---|
| Broad equity trend | $136.29 | $113.51 | $107.43 | Pass |
| Cross-asset ETF rotation | $91.43 | $129.60 | $138.48 | Fail: older-window loss |
| Direct-stock rotation | $191.05 | $164.86 | $100.75 | Fail: drawdown and recent stress return |
| BTC/ETH rotation | $129.53 | $194.44 | $84.51 | Fail: drawdown and recent loss |
| SPY buy-and-hold benchmark | $173.29 | $121.78 | $129.53 | Benchmark only |
| BTC buy-and-hold benchmark | $319.46 | $195.58 | $92.11 | Benchmark only |

Broad equity trend maximum drawdowns were 14.88%, 23.35%, and 9.22%, with 78 completed round trips combined. Direct-stock rotation touched $200 in the oldest window before finishing below it. Crypto rotation touched $200 in 2024 but its oldest-window drawdown was 88.24%. A temporary milestone touch without modeled milestone liquidation is not a completed milestone lifecycle.

The batch contains 36 paths: four candidates, two benchmarks, three windows, two cost assumptions. Complete ledgers and equity paths are in results.json; compact outcomes are in summary.json. PLAN.md was frozen before outcomes. All 442 repository tests passed; test-results.txt contains the run.

Limitations: retrospectively chosen universes/windows, omitted dividend cash, incomplete historical fractional-trading eligibility reconstruction, settlement calendar omits bank-only holidays, and Coinbase candles are a crypto venue proxy. Monthly exits have no hard stop and cannot use evidence for the existing DAY-stop worker. Maker queue position, partial fills, and venue-specific execution are not modeled. These results are historical screens, not forward or live verification.

Options approval was level 3 but OPRA snapshots returned HTTP 403 because the OPRA agreement is unsigned. No option P&L was fabricated from underlying prices. Direct bonds and mutual funds remain untested without a verified account/adapter route. Bond ETFs were included in cross-asset rotation. Alpaca support subsequently confirmed Florida crypto ineligibility; see ../20260924-crypto-alternatives/DECISION.md for the alternative venue research.
