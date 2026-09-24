# First-stage whole-share breakout result — September 23, 2026

The frozen [rule](../backend/app/research/whole_share_breakout_stage_v1.py)
tested the **$100 → $500** waypoint, not the entire capital ladder. It scans
F and SOFI for a 20-session high with at least 1.5 times trailing volume,
enters at the next open using affordable whole shares and up to 100% of cash,
and models a 4% stop, 8% target, or exit after ten sessions. It deducts 0.1%
of entry notional per completed round trip. Daily account equity includes
cash days and marks any open position.

| Window | Completed trades | Final equity from $100 | Maximum drawdown | Touched $500 |
| --- | ---: | ---: | ---: | --- |
| 2023–2024 development | 17 | $98.68 | −19.90% | No |
| 2025–September 22, 2026 | 12 | $91.52 | −18.93% | No |

The evaluator was committed as `2956740` before these data were read.
Source: Alpaca adjusted IEX daily bars, F 1,183 bars and SOFI 1,184 bars,
January 3, 2022–September 22, 2026. SHA-256 of the exact local JSON data:
`5ae028b8bddd10c63fa19a96598731967dd430f6adec4655ac2961d9146121c8`.
The two windows were computed separately with a 20-session warmup. No
parameter was retuned after observing the results.

This exact rule fails the first milestone even with full account allocation.
Daily OHLC bars cannot establish actual stop or target ordering, fill quality,
or broker acceptance. Gap-down exits use the observed open when it is below
the stop. The result is a research rejection, not a live-trading approval.
The account's existing production risk caps were not changed.
