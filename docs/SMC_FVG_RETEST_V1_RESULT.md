# SMC fair-value-gap retest v1 — result (26 September 2026)

The [frozen rule](SMC_FVG_RETEST_V1_PLAN.md) was committed before any evaluation data was downloaded and was run unchanged. **Result: FAIL.** No tuning followed.

Data: Coinbase Exchange public 1-minute candles, BTC/ETH/SOL-USD, 2026-03-22 → 2026-09-22 UTC. 264,513–264,530 candles per coin; 430 / 437 / 447 minutes absent at the venue (≈0.17%). Candle SHA-256: `c9f566c60f1d90f2c47cffcfe13e93be50b9dbe40533fd9de4abbff38b2fb191`. Full output: [SMC_FVG_RETEST_V1_RESULT.json](SMC_FVG_RETEST_V1_RESULT.json). Reproduction: `python -m app.research.run_smc_fvg_retest_v1` from `backend/`.

The research port matched the original Apex engine exactly on 8 synthetic 4,000-bar series (147 long signals, 0 differences in index, stop or target).

| Window (primary 0.25% fee + 0.05% slippage per leg) | Signals | Trades | End equity | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| Development 2026-03-23 → 06-22 | 1,876 | 0 | $100.00 | — | 0% |
| Confirmation 2026-06-22 → 09-22 | 1,905 | 1 (stop) | $99.17 | 0 | 0.8% |

Fee sensitivity on the same trades (confirmation): $99.64 at 0%, $99.45 at 0.10%, $98.22 at 0.75%. Stage assessment ($100 → $500, 183 days, 10,000 block paths): 0 paths reached $500; median path ending $99.17.

## Why it barely traded

1. **Across the full series, 99.8% of signals (3,783 of 3,791, warm-up included) set the target at exactly 3R**, because the nearest swing high rarely gives ≥ 3R. Any fill above the signal close (the next open plus 0.05% slippage, median +0.05%) pushes R:R below 3, so the frozen drift check rejects it: 3,511 of 3,781 signals. The live Apex engine has the same check against the live price, so it would behave the same way.
2. **The median stop is 0.169% of price**, below the 0.30% fee-drag floor. At 0.25% per leg, fees plus slippage for a round trip (0.60%) cost about 3.5R; the single trade lost −2.7R when its stop was hit at a nominal −1R.
3. The remaining signals arrived while another coin's entry was pending or open (268).

## Conclusion

This exact rule cannot fund the $500 waypoint on 1-minute spot crypto at retail costs: it either does not trade or trades with stops smaller than its costs. The result does not show that every SMC formulation fails. A variant that sets the target from the actual fill, requires a stop of at least several times round-trip cost, or runs on a higher timeframe would be a **new version**. It must be frozen before testing and evaluated on data v1 has not seen (for example 2025-09-22 → 2026-03-22). No paper or live promotion follows from v1.
