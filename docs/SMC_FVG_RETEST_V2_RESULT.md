# SMC fair-value-gap retest v2 — result (27 September 2026)

The [frozen v2 rule](SMC_FVG_RETEST_V2_PLAN.md) was committed before any v2 data was downloaded and was run unchanged. **Result: FAIL.** No tuning followed.

Data: Coinbase Exchange public 15-minute candles, BTC/ETH/SOL-USD, 2025-09-01 → 2026-09-22 UTC, 37,008 bars per coin (48 absent at the venue per coin). SHA-256 `f4cf31ed1dd5b590905ce180d990a62a1b651400db5a88ed2c5cb1cbe1e580b3`. Output: [SMC_FVG_RETEST_V2_RESULT.json](SMC_FVG_RETEST_V2_RESULT.json). Reproduction: `python -m app.research.run_smc_fvg_retest_v2` from `backend/`. v1 reproduces byte-identically after the shared module gained v2's default-off options.

| Window (0.25% fee + 0.05% slippage per leg) | Signals | Trades | Win rate | Avg R | PF | End | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Development 2025-09-22 → 12-22 | 102 | 14 | 14.3% | −0.66 | 0.38 | $82.77 | 21.6% |
| Confirmation 2025-12-22 → 2026-03-22 | 125 | 17 | 23.5% | −0.29 | 0.65 | $89.75 | 16.9% |
| *Supplementary: v1 window 2026-03-23 → 09-22 (contaminated)* | 261 | 11 | 36.4% | +0.22 | 1.19 | $103.16 | 14.8% |

**Fee sensitivity (same trades):**

- Development: $87.88 at zero cost, $85.80 at 0.10%, $73.37 at 0.75%.
- Confirmation: $96.35 at zero cost, $93.66 at 0.10%, $77.79 at 0.75%.

**Stage assessment** ($100 → $500 over the 181 combined untouched days, 10,000 five-day block paths): 0 paths reached $500 and 0.37% touched the $50 floor. Median path ending $74.20; the observed path ended at $74.28.

## Reading

- The fill-anchored target removed v1's drift rejections completely (0 drift skips). The 1.80% stop floor removed most signals: 56 of 102 and 81 of 125.
- Both untouched windows **lose even at zero trading cost** (profit factor 0.49 and 0.85). The win rates of 14% and 24% sit below the 25% break-even of a 3R payoff, before costs, so fees are not what made v2 fail.
- Fewer than the required 30 trades occurred in each window. Six months of three coins produce too few qualifying setups to compound $100 toward $500, even if the edge were positive.
- The positive supplementary window was the period whose v1 outcome shaped v2. It is below the profit-factor gate and is not evidence of an edge.

## Conclusion

Neither the 1-minute (v1) nor the 15-minute (v2) formulation of this SMC sweep → MSS → FVG-retest rule shows a gross edge on BTC/ETH/SOL spot in these windows. Further SMC variants on the same assets would be a search over parameters on data that has now been examined, with a growing multiple-testing penalty. No paper or live promotion follows.
