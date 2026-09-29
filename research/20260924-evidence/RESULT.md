# Strategy evidence result — September 24, 2026

**Result: the fixed monthly ETF candidate did not pass its historical screen.**
The former older-data blocker is resolved. The frozen V3 rules and settlement-corrected V4 were each run across three fixed windows and three costs: 18 runs total. No parameter search or live order was performed.

| V4 window | Round-trip cost | Completed trades | $100 ending equity | Return | Maximum drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2017-2021 | 0.1% | 50 | $88.49 | -11.51% | -26.59% |
| 2017-2021 | 0.2% | 50 | $84.99 | -15.01% | -28.74% |
| 2017-2021 | 0.5% | 50 | $79.15 | -20.85% | -31.60% |
| 2022-2024 | 0.1% | 30 | $110.88 | +10.88% | -23.73% |
| 2022-2024 | 0.2% | 30 | $108.53 | +8.53% | -24.52% |
| 2022-2024 | 0.5% | 30 | $106.33 | +6.33% | -22.80% |
| 2025-2026 | 0.1% | 19 | $106.22 | +6.22% | -12.47% |
| 2025-2026 | 0.2% | 19 | $104.84 | +4.84% | -13.50% |
| 2025-2026 | 0.5% | 19 | $100.71 | +0.71% | -16.60% |

Neither $200 nor $500 was touched in any of the 18 paths. These are marked-equity observations, not actual liquidation proceeds. The 2017–2021 and 2025–2026 paths end with an open position; 2022–2024 ends flat.

## Why the screen failed

The predeclared V4 criteria require positive net modeled return in all three windows and drawdown better than 25% in each. The older window returned -11.51% and drew down 26.59% at 0.1% round-trip costs. The recent window met its 10-trade minimum and remained positive at 0.2% cost. The candidate therefore fails on the older window; this is not a rejection for failing to demonstrate the entire milestone ladder.

## Data and execution evidence

- Downloaded raw and officially split-adjusted Alpaca SIP daily bars through the existing non-submitting paper adapter. Only market-data and calendar GET requests were used.
- All 14 instruments cover every one of the 2,695 broker-calendar sessions from January 4, 2016 through September 22, 2026. The API also returned September 23; it was excluded to honor the frozen exclusive end date. Original response is preserved.
- Raw/split ratios identify XLE and XLU 2-for-1 events on December 5, 2025. EWU and EWJ reverse splits occurred only in the 2016 indicator warmup, before any modeled holdings; official signal adjustments handle them. No reverse-split holding is simulated.
- V4 delays monthly re-entry for historical T+3/T+2/T+1 settlement. V3 remains unchanged for comparison. Stops take the worse opening price on gaps. Cost assumptions are 0.1%, 0.2%, and 0.5% of notional round trip, not verified historical spreads.
- Eight new deterministic tests cover settlement transition dates, whole-share entry timing/affordability, gap-through-stop exits, and the account breaker. Full suite results are in test-results.txt. These are simulator/unit tests, not broker fills.

## Limits and exact next evidence needed

Dividend cash credits are excluded. These are price-plus-modeled-cost results, not complete total returns; omitted distributions may materially change the older result. The current universe was selected using prior research, so the older window is newly retrieved project evidence, not a pristine forward holdout. Daily bars do not establish intraday execution sequence, actual spread, order acceptance, or corporate-action behavior at the broker. Settlement delays count trading sessions and do not yet model bank-only settlement holidays. The 20% breaker triggers a next-open exit; gaps can exceed that threshold, as the measured drawdown shows.

No candidate is promoted and no production validation record is altered. A defensible next test would first add dated distribution cash flows and settlement-calendar fidelity to this same frozen rule, then evaluate it without parameter changes. A real paper-broker lifecycle would be separate evidence; no claim of one is made here. The predeclared matrix is complete and stopped as planned.

## Reproduce

From the repository root: `PYTHONPATH=backend .venv/bin/python research/20260924-evidence/run_matrix.py`. Source data, full equity paths, trade ledgers, flat comparison CSV, and hashes are retained alongside this report.

## Sources

- [Alpaca historical data and adjustment reference](https://alpaca.markets/learn/fetch-historical-data)
- [Alpaca market-data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)
- [SEC September 5, 2017 T+2 implementation](https://www.sec.gov/newsroom/press-releases/2017-163)
- [SEC May 28, 2024 T+1 transition](https://www.sec.gov/compliance/risk-alerts/shortening-securities-transaction-settlement-cycle)
- [Alpaca fractional DAY-order restriction](https://docs.alpaca.markets/us/docs/fractional-trading)
