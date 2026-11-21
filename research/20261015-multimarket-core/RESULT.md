# Multi-market core test — RESULT: FAIL (2026-10-15)
Rules as in PLAN.md; mcore.py (run from the daily-data directory with scan_bt.py / rot_curve.py).

| From $100 | Dev 2019–2023 | Max DD | Conf 2024–Sep 2026 | Max DD | 12-mo floor risk | COVID / 2022 low |
|---|---|---|---|---|---|---|
| Live allocator (TQQQ core) | $331 | 53% | $217 | 39% | 1.6% | $61.91 / $51.88 |
| MC1 top-2 markets, unleveraged | $139 | 27% | $189 | 15% | 0.0% | $79.44 / $86.27 |
| MC2 top-2 markets, leveraged | $146 | 37% | $173 | 24% | 0.7% | $66.02 / $79.11 |

- Both fail rule 1 in development: 2019–2023 rewarded holding the Nasdaq, and rotating across markets earned less than half.
- In confirmation MC1 met the rule (87% of the allocator with drawdown 24 points smaller) — but the rule requires both periods.
- Both pass the stress gate easily.
- Verdict: FAIL; the TQQQ core stays. The trade-off (much smaller drops, much lower upside in Nasdaq bull runs) is an owner risk choice, not a test result.
