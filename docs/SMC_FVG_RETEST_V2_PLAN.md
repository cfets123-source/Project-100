# SMC fair-value-gap retest v2 — research plan (frozen before outcome)

Predecessor: [v1](SMC_FVG_RETEST_V1_PLAN.md) failed ([result](SMC_FVG_RETEST_V1_RESULT.md)). It rarely traded because targets were fixed from the signal close, so any entry slippage broke the 1:3 check. When it did trade, its 1-minute stops (median 0.17%) were smaller than the 0.60% round-trip cost. v2 changes only those three mechanical causes. It is frozen here before any v2 evaluation data is downloaded or any v2 signal is computed.

## Changes from v1 (everything else is identical)

1. **Timeframe:** Coinbase **15-minute** candles instead of 1-minute. The higher-timeframe filter uses completed **1-hour** buckets (4 × 15 minutes) instead of 5-minute buckets. Window (240 bars), sweep expiry (30 bars), swing definition, FVG size filter (0.10 ATR14) and the 20/120-bucket filter rule keep v1's bar counts.
2. **Target anchored to the fill:** the R multiple is fixed at the signal (3R, or the nearest swing-high multiple between 3R and 8R). At entry the target is set to `fill + multiple × (fill − stop)`. The entry is skipped only if the fill is at or below the stop.
3. **Minimum stop distance = 3 × primary round-trip cost:** (0.25% fee + 0.05% slippage) × 2 legs × 3 = **1.80%** of the fill. This stays fixed at 1.80% in the fee-sensitivity runs, so the same trades are compared.

Unchanged: long-only, one position across BTC/ETH/SOL (priority BTC, ETH, SOL), entry at the next bar's open + 0.05%, 2% equity risk capped at 95% notional, $1 minimum, stop-first when a bar touches both levels, stop or gap-open fills less 0.05%, 5% daily breaker with a 24-hour halt, close at window end, and no Claude supervisor modeled.

## Data and windows (untouched by v1)

Coinbase Exchange public 15-minute candles, BTC-USD, ETH-USD and SOL-USD. Record the candle SHA-256 and missing bars.

- Warm-up: 2025-09-01 → 2025-09-22 UTC (signals only).
- **Development:** 2025-09-22 → 2025-12-22 UTC.
- **Confirmation:** 2025-12-22 → 2026-03-22 UTC.

Each window starts a fresh $100 account.

**Supplementary, not used for the pass decision:** the same frozen v2 rule replayed on v1's windows (2026-03-23 → 2026-09-22). v1's outcome on that period shaped these changes, so it is reported as contaminated evidence only.

## Reported measures and pass condition

Same as v1: ending equity, net return, trades, win rate, average R, profit factor, maximum drawdown, whether $500 was reached, daily returns including flat days, and fee sensitivity at 0%, 0.10% and 0.75% per leg. Stage assessment on the combined development + confirmation path: $100 → $500, $50 floor, horizon equal to the observed days, five-day blocks, 10,000 paths, seed 20260927.

**Pass (primary cost, both windows):** positive net return, profit factor ≥ 1.2, at least 30 trades, maximum drawdown ≤ 35%.

Passing earns an exact-code paper lifecycle only. Failing is recorded and not tuned away.
