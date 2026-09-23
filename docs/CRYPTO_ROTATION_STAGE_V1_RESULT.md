# Crypto rotation opening-stage result — 23 September 2026

The [predeclared rule](CRYPTO_ROTATION_STAGE_V1_PLAN.md) was run over **365 complete UTC days, 22 September 2025–21 September 2026**. The [daily net account-return record](CRYPTO_ROTATION_STAGE_V1_DAILY_RETURNS.json) is the exact input to the stage assessment; it includes all 189 cash days. [Reproduction script](../backend/app/research/run_crypto_rotation_stage_v1.py) fetches Coinbase Exchange public daily candles and verifies that none of the required dates are missing. Source-candle SHA-256 for this run: `ee7de4cacd94f9f0ab898fe816a864159942a8c76fbfb644f377e8c1ed48f4c0`.

| Measure | Result |
| --- | ---: |
| Starting account / opening milestone | $100 / $1,000 |
| Observed ending account after modeled costs | **$39.91** |
| Observed $1,000 milestone | Not reached |
| Observed maximum drawdown | 63.48% |
| Entries / exits | 46 / 45 |
| One-way cost assumption | 0.75% per traded leg |
| Five-day block resamples that reached $1,000 | 0 / 10,000 |
| Resamples that crossed $50 | 7,699 / 10,000 |
| Resampled ending account, 10th / 50th / 90th percentile | $22.95 / $40.24 / $70.00 |

Cost sensitivity for **the same selections**, with no new strategy tuning: $79.17 at zero trading cost, $63.04 at 0.25% per leg, $50.17 at 0.50% per leg, and $39.91 at the predeclared 0.75% per leg. Even the zero-cost path lost money in this window. The recorded path did not meet the first milestone. Zero target hits in historical resamples means none appeared under this particular resampling method; it is not a zero probability claim about the future.

This is exploratory research using Coinbase daily opens as a proxy for a Robinhood-tradable four-coin basket. It has no Robinhood bid/ask, fill, funding, or execution evidence and cannot authorize live deployment. The study does not establish that other rules or assets will fail. It establishes that **this fixed rule and window** did not support the $100 → $1,000 opening stage.

Data source: [Coinbase Exchange candle API](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles). The venue warns that historical candles may be incomplete; this run required every expected day. [Robinhood supported crypto list](https://robinhood.com/us/en/support/articles/coin-availability/).
