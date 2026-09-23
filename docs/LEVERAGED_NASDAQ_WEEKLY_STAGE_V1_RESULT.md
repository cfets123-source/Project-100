# Leveraged Nasdaq weekly rotation: milestone result, 23 September 2026

The [fixed rule](LEVERAGED_NASDAQ_WEEKLY_STAGE_V1_PLAN.md) was run against ProShares' [issuer-published historical NAV changes](https://prod.proshares.com/resources/data-downloads). The [daily net account returns and source changes](LEVERAGED_NASDAQ_WEEKLY_STAGE_V1_DAILY_RETURNS.json) preserve the exact data used. The [script](../backend/app/research/run_leveraged_nasdaq_weekly_stage_v1.py) verifies that the two funds have matching trading dates, enough prior observations, and internally consistent NAV changes. It uses NAV percentage changes to avoid treating an ETF split as a trade profit. The full downloaded source CSV SHA-256 is `afb816bf493f0e2ce0cff11c63d4229ffa6d0a62171f1b772d8ce0cee8198447`.

| $100 opening account | Earlier comparison: 2024-09-23–2025-09-19 | Later period: 2025-09-22–2026-09-21 |
| --- | ---: | ---: |
| Trading sessions | 249 | 251 |
| Weekly rotation ending account, net of modeled cost | $115.77 | **$84.66** |
| First $500 waypoint / first $1,000 waypoint | Neither reached | Neither reached |
| Maximum drawdown | 50.82% | 35.53% |
| Entries / exits | 11 / 10 | 16 / 15 |
| Cash days | 18 | 24 |
| Same rotation selections at zero cost | $122.02 | $91.49 |
| TQQQ hold-only NAV comparison, zero transaction cost | $148.34 | $154.26 |
| SQQQ hold-only NAV comparison, zero transaction cost | $39.38 | $44.19 |
| Five-session resamples touching $500 | 186 / 10,000 | 11 / 10,000 |
| Five-session resamples touching $1,000 | 6 / 10,000 | 0 / 10,000 |

This timing rule lagged TQQQ buy-and-hold in both years and lost money in the later period. Neither period reached the first $500 waypoint. The block resamples are descriptions of the supplied sequence, not future success rates. ProShares warns that daily leveraged and inverse funds need not deliver their stated multiple over longer holding periods; the daily reset and volatility affect compounded returns. The test uses issuer NAV rather than exchange order fills and excludes distributions, taxes, and broker-specific execution costs. The 0.25%-per-leg cost is a fixed research assumption, not a verified Alpaca quote or fee.

This result does not justify making the live worker trade TQQQ or SQQQ. The useful lesson is specific: neither a larger account-risk fraction nor splitting the first target into $500 and $1,000 fixes a rule whose selected positions underperform the passive comparison. A new opening-stage candidate needs a different, testable source of payoff, broker-accessible data, and a separate untouched confirmation window.
