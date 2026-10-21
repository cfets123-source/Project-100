# Intraday test — RESULT: FAIL (2026-10-13)
Run on the server (Alpaca SIP 5-minute bars, 1,945 sessions 2019-01-02..2026-09-30), rules exactly as in PLAN.md.

| | Dev 2019–2023 | Conf 2024–Sep 2026 | At 0.06% cost (dev / conf) | Max DD (dev / conf) | 12-mo floor risk | Verdict |
|---|---|---|---|---|---|---|
| Allocator (benchmark) | $331 | $217 | — | 53% / 39% | 1.6% | live |
| ORB5 | $84.77 | $76.22 | $40.06 / $50.53 | 50% / 43% | 1.7% | FAIL (loses money) |
| NOISE | $207.73 | $138.06 | $103.13 / $93.64 | 24% / 28% | 0.0% | FAIL (below allocator; break-even at 0.06%) |

- ORB5 wins 23–25% of days and loses money in both periods even at base cost.
- NOISE makes money at 0.03% per side with much smaller drawdowns, but trails the allocator in both periods and
  roughly breaks even when costs double, so its edge is about the size of trading costs.
- Per the plan, no variants are tried on this data. The allocator stays as the live strategy.
- Possible follow-up (new evidence only): forward paper-trade NOISE to measure real fill costs on data after 2026-09-30.
