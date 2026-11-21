# Stress-test gate — 7 October 2026

**Gate, fixed before running:** a strategy may be approved for live money only if:
- in a 4,000-path Monte Carlo of the next 12 months, it touches the $50 floor in no more than 10% of paths. The paths are built by resampling 20-day blocks of the backtest's own daily returns; and
- starting from $100, the account never falls to $50 during any listed historical crash window.

| Strategy | Sample | Chance of touching $50 | 12-month range (5th / median / 95th percentile) | Crash windows (lowest value, from $100) | Result |
|---|---|---|---|---|---|
| allocator-core-satellite-v1 (50% TQQQ + 5 satellites, weekly swap) | 2011–Sep 2026 | 1.6% | $68 / $123 / $210 | COVID crash $61.91 · 2022 bear $51.88 · Q4 2018 $64.66 | PASS |
| binance-crypto-signals-v1 (BTC/ETH/SOL signals) | 2018–Sep 2026 | 0.0% | $80 / $130 / $232 | 2018 crypto winter $95.38 · March 2020 $100 · 2022 crypto bear $83.87 | PASS |

**Caveats:**
- Both curves are in-sample, built on the same history the rules came from.
- The stock list carries survivorship bias, because it is made of today's large companies.
- Prices are marked at daily closes, so intraday drops and gaps are understated.
- The allocator came within $1.88 of the floor in the 2022 bear market.

Machine-readable results, including daily-return bands for the nightly review, are in `backend/app/research/stress_results.json`, which the app reads. Scripts: `stress.py`, which uses `rot_curve.py`/`cbt_curve.py` and the cached Yahoo daily data.
