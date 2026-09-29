# Frozen evidence test — September 24

Before obtaining new returns, test one existing positive-development candidate:
monthly whole-share ETF momentum V3. Do not search new parameters or pick the
best period. Frozen 14-ETF universe, 252-session ranking, 200-session trend,
95% cash cap, 10% stop, 20% account breaker and 63-session cooldown remain fixed.

Execution-corrected variant V4 changes only settlement: three sessions before
2017-09-05, two before 2024-05-28, one thereafter. Monthly exit first session;
entry after the applicable settlement delay. No borrowing unsettled proceeds.
Use $100 starting cash, raw consolidated SIP daily bars for whole-share execution
and official split-adjusted bars for signals. Infer held-position split changes
from the ratio of those two matched series, rejecting non-integer/ambiguous
changes. Do not infer splits from price jumps alone. Require calendar-complete
input across the fixed universe and 252 prior sessions. Dividend credits are
excluded and must be disclosed. Execution remains a daily-bar approximation.

Request 2016-01-01 through 2026-09-23. Fixed windows: 2017–2021, 2022–2024,
2025–2026-09-23 exclusive. The first window was unavailable to the old IEX test;
confirm coverage before evaluation. The later two were already inspected and
are development robustness checks. Existing strategy/universe selection means
this is not a pristine forward holdout.

Run V3 reproduction and V4 at 0.1%, 0.2%, and 0.5% round-trip notional costs.
V4 primary screen retains positive returns in all three windows at 0.1%,
drawdown better than 25% in each, at least 10 completed recent trades, and
positive recent return at 0.2%. Report the 0.5% case without changing the gate.
Report $200 and $500 touches, ending marked equity, turnover, skipped entries,
and open positions separately; reaching a milestone is not assumed liquidation.
Zero cash return is the basic capital-preservation comparison.

Stop after this fixed matrix. If it fails, preserve failure without tuning.
If it passes, classify as a historical research candidate, then run deterministic
execution tests with broker doubles. Neither backtests nor doubles establish
real broker fills or authorize live trades. No order endpoint is used, no
production strategy record is changed, and no execution flag is enabled.
