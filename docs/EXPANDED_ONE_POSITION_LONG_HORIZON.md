# Expanded one-position strategy: long-horizon check

On September 23, 2026, the unchanged `daily-trend-pullback-expanded-equity-etf-v1` evaluator was rerun against all paginated Alpaca adjusted IEX daily bars available through September 22. The requested history began January 2016; the 79 instruments returned 122,036 bars, with the earliest available series starting April 25, 2018. The fixed out-of-sample split remained January 1, 2023. This rerun reproduced the existing validation record exactly: **126 completed trades, +22.54% compounded modeled return, -10.08% maximum drawdown, and a passing result** under the previously specified thresholds. The record was refreshed in the production research ledger. No strategy parameters were changed. **This is a historical overnight-hold result, not a live-execution pass.** The fractional-share live worker must close before its DAY stop expires. See [the session-matched diagnostic](SESSION_MATCHED_DAILY_PULLBACK_2025_2026.md).

| Exit year | Completed trades | Compounded modeled return |
| --- | ---: | ---: |
| 2023 | 28 | +13.19% |
| 2024 | 38 | +17.25% |
| 2025 | 44 | -6.42% |
| 2026 through September 22 | 16 | -1.34% |

The negative 2025 and 2026 segments do not by themselves invalidate the multi-year overnight result. They do show that recent performance has weakened, and the long-run positive result is not evidence of high intraday trade frequency. The separately tested two-position variant lost money, and the high-frequency opening-range candidate lost money across its full annual follow-up. Neither inherits this one-position strategy's passing record. The expanded live route is disabled because its historical holding period does not match the worker's same-day fractional exit.
