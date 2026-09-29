# Daily liquid momentum first-stage result

The [rule and account model](DAILY_LIQUID_MOMENTUM_STAGE_V1_PLAN.md) were frozen before this read-only evaluation. Robinhood Agentic split-adjusted, regular-session daily OHLCV was requested for SOFI, F, PLTR, TQQQ, and SQQQ from October 2, 2023, through September 23, 2026. Each symbol returned 747 aligned bars with no `interpolated` bars or missing volume. October–December 2023 supplied warmup only. The test used no broker orders.

| Period | Completed trades | Candidate signals | Unaffordable next-open entries | Final equity from $100 | Max drawdown | First $500 touch |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2024 development | 18 | 24 | 4 | $104.77 | -16.80% | None |
| Jan 2025–Sep 23 2026 confirmation | 16 | 29 | 11 | $74.12 | -28.69% | None |

In confirmation, three of 16 trades were profitable; 11 exited at stops, two at targets, and three at the fifth-session limit. The predeclared 0.4% round-trip cost stress also ended near $74.12; different integer-share sizing changed the subsequent trade path. Both results failed the first $500 waypoint and the positive-net-return screen. The 29 candidate signals did not translate into a high-volume trading path: 11 selected entries were unaffordable at the next open. Signals while a position was held were not counted as candidate opportunities.

This is a daily-bar model, not broker execution proof. The later chronological period had already been examined during related Project 100 research, so it is not pristine untouched confirmation. The model cannot reproduce bid/ask spread, stop slippage beyond modeled opening gaps, partial fills, or actual protective-order acceptance. The five-symbol universe was selected with current knowledge, so survivorship and selection bias remain. The negative later-period result is enough to reject this exact candidate for live promotion; the 2024 gain should not be used to authorize it. No live setting, service, or order was changed.
