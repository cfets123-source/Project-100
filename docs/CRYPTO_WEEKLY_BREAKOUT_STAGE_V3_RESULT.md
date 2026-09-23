# Weekly crypto breakout: milestone result, 23 September 2026

The [V3 rule](CRYPTO_WEEKLY_BREAKOUT_STAGE_V3_PLAN.md) was frozen after the V2 eight-coin study failed its data-completeness check; PEPE and WIF each lacked 85 daily candles at the start of the earlier window. V3 retained the same weekly rule and costs with a six-coin universe that had full coverage. Its [daily net account returns](CRYPTO_WEEKLY_BREAKOUT_STAGE_V3_DAILY_RETURNS.json) include every day in both 365-day windows. The [reproduction script](../backend/app/research/run_crypto_weekly_breakout_stage_v3.py) checks full source coverage. Source-candle SHA-256: `26ac334f51807128432df1d31f71aa67872a63dd8bf29e99ba08ae23b12531ce`.

| $100 opening account | Earlier comparison: 2024-09-22–2025-09-21 | Later period: 2025-09-22–2026-09-21 |
| --- | ---: | ---: |
| Ending account after modeled cost | $186.18 | **$24.39** |
| First $500 waypoint | Never reached | Never reached |
| First $1,000 waypoint | Never reached | Never reached |
| Maximum drawdown | 64.46% | 78.64% |
| Entries / exits | 17 / 16 | 15 / 14 |
| Cash days | 99 | 147 |
| Same selections, zero cost | $238.68 | $30.35 |
| Five-day resamples touching $500 | 2,497 / 10,000 | 0 / 10,000 |
| Five-day resamples touching $1,000 | 876 / 10,000 | 0 / 10,000 |
| Five-day resamples crossing $50 | 2,679 / 10,000 | 9,204 / 10,000 |

The earlier year's positive account return still did not reach the first $500 waypoint. The following year lost money even before modeled transaction costs. Splitting $100 → $1,000 into $100 → $500 → $1,000 makes the handoff measurable but does not make this rule pass either step. Historical block fractions describe these two observed return sequences; they are not probabilities of future success.

This test gives no basis to promote the rule to paper or live. It uses [Coinbase Exchange historical daily candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) as a proxy for six coins on [Robinhood's supported list](https://robinhood.com/us/en/support/articles/coin-availability/). Actual venue spreads, fills, funding, permissions, and historical tradability were not tested. Coinbase warns that historical candles can be incomplete; the script rejected missing days. The 0.75%-per-leg cost is an assumption; [Robinhood's published crypto fee tiers](https://robinhood.com/us/en/support/articles/crypto-fee-tiers/) vary by account volume and route.

The useful boundary from this study is that simply adding more spot-crypto names and rotating weekly did not solve the opening-stage problem. The next research route must offer a genuinely different payoff structure and an execution-matched price record; tuning this weekly rule to the better of these two years would reuse already-inspected data.
