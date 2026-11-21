# Multi-market test — 2026-10-26

Same bot rules (NOISE, hourly checks, 1% vol sizing), 5-min data 2019-01 → 2026-10.
Proxies: SPY→MES, IWM→M2K, GLD→MGC. DEV = 2019–23 (tuning), CONF = 2024–26 (unseen). A market must be positive in both.
Prop EV = expected $ per Topstep 50K attempt, risk scaled to MNQ-equivalent notional.

| Market | DEV EV | CONF EV | CONF Sharpe | corr w/ QQQ |
|---|---|---|---|---|
| MNQ (QQQ) — current | +$1,334 | +$296 | 1.10 | — |
| MES (SPY) | +$626 | −$149 | 0.05 | 0.69 |
| M2K (IWM) | −$256 | −$258 | −0.57 | 0.32 |
| MGC (GLD) | −$134 | +$26 | 0.73 | 0.00 |
| MNQ+MGC split | +$235 | +$403 | 1.32 | |
| MNQ + ½ MGC on top | +$655 | +$181 | | |
| All four split | +$212 | −$142 | 0.48 | |

## Verdict
- Keep the bot on MNQ only. No other market passes both periods.
- M2K: no edge in either period. MES: edge disappeared after 2023 and is highly correlated with MNQ.
- MGC is uncorrelated and helped in 2024–26, but lost money in 2019–23. The 2024–26 gain looks like gold's one-way rally, not a repeatable edge. Re-test in 6 months.
