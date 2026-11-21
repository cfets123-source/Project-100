# London-session test (2026-10-23) — QQQ pre-market 5-min bars 2019-2026, flat by 9:25 ET
| Strategy | 2019-2023 (mean/day, Sharpe) | 2024-2026 | Verdict |
|---|---|---|---|
| L1 NOISE rules on the 4:00 open, hourly checks | -0.26bp, -0.12 | +2.15bp, 1.40 | fails build period |
| L2 4:00-5:00 range breakout | -2.12bp, -0.65 | +0.92bp, 0.35 | fails |
| L3 Pre-market drift: at 8:00 go with the move since the prior close, exit 9:25 | +1.24bp, 0.41 | **+4.70bp, 2.15** | positive both periods, weak early |
| NY bot (hourly + vol sizing) for reference | +4.52bp, 1.63 | +3.45bp, 1.17 | |
| NY + L3 combined | +5.76bp, 1.43 | **+8.15bp, 2.25** | correlation with NY -0.03 |
L3 is uncorrelated with the NY strategy and adds profit in both periods; in 2024-26 it more than doubles the
risk-adjusted return. Caveats: QQQ pre-market prices proxy MNQ futures; build-period edge is small. Next: check on the
MNQ futures history from TopstepX and run L3 in dry run alongside the live bot before any real orders.

## MNQ futures check (TopstepX history, Aug 24 - Oct 22 2026, 42 days)
L3 on real MNQ: -3.47bp/day, win 40.5% (small sample). On 25 overlapping days QQQ and MNQ gave the same sign 24 times
(proxy is valid), but both were negative in this stretch (QQQ -4.0bp, MNQ -9.8bp). A 2-month losing stretch is
consistent with a Sharpe ~2 strategy about 30% of the time, so this neither confirms nor kills it.
Decision: do not trade L3 with real orders yet; run it in dry run alongside the live bot and review after ~6 weeks.
