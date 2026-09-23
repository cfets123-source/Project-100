# Whole-share overnight pullback v1: recent confirmation failed

Commit `1c86bed` froze the exact 79-symbol selection and $100 cash/integer-share portfolio evaluator before its result was inspected. This variant differs from the fractional live worker: it assumes a whole-share GTC stop can remain active across sessions, models stop-first daily bars and adverse gaps, and limits each entry by cash, 65% maximum exposure, and a 2% account risk budget. It never places an order.

| Period | Completed trades at 0.1% cost | Modeled account return at 0.1% cost | Maximum drawdown |
| --- | ---: | ---: | ---: |
| 2023 development | 35 | +15.03% | -9.54% |
| 2024 development | 34 | -4.68% | -18.70% |
| 2025 recent confirmation | 37 | -12.45% | -16.47% |
| 2026 through September 22 | 18 | +8.35% | -7.86% |
| 2025–2026 combined | 55 | -5.14% | -17.49% |

The 2023 row begins after the 50-session indicator warmup. The recent combined period failed the predeclared positive-return gate and was also -3.14% under the 0.2% round-trip cost stress. Thirty-eight signal days were unaffordable at the modeled equity and risk limits. The sample ends with a marked open position, so the September 22 account value includes unrealized P&L rather than a completed broker exit. These daily-bar results do not prove actual GTC-stop acceptance, fill quality, or paper lifecycle. This exact strategy version is not eligible for paper execution or live capital on the stated gate.

The 2023–2024 mixed result and positive 2026 segment are worth retaining for regime analysis; they do not offset the negative recent confirmation for this frozen route. A future candidate must be versioned separately and tested on fresh data or forward paper evidence rather than tuning this one against the periods already inspected.
