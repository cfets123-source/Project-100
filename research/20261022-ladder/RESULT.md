# Full ladder validation — first round (2026-10-22)

Data: QQQ 5-min (Alpaca SIP) 2019-01 → 2026-09, 1,934 days, run through the bot's own decision code (prop/noise.py).
Proxy check: on 17 overlapping days QQQ and real MNQ (TopstepX history) gave the same day result on 16; 10/22 live dry
run +$834 vs simulated +$822. Rules: Topstep as published Oct 2026 (Combine target/consistency, trailing MLL on EOD
high, MLL set to $0 after first XFA payout, 5 winning days ≥$150, 50%/size payout caps, 90% split, $125 minimum,
5 XFA max, fees $49/$99/$149 monthly, $149 activation, $14.50 API). All accounts trade the same signal (correlated).
Simulation: 20-day block bootstrap, 400 paths per scenario; owner money capped by a budget (ruin = budget exhausted
with nothing alive).

## Single-account economics (historical starts, full period)
- 50K Combine, 2 contracts: 36% pass, median 24 days, cost per pass ≈ $352 (incl. activation).
- 150K Combine, 6 contracts: 28% pass, median 22 days, cost per pass ≈ $822.
- Funded 50K, original bot policy (2 contracts, $400 buffer, 50% payouts): avg $1,334 lifetime payouts, median $0.
- Funded 50K, v2 policy (1 contract until room ≥ $5k, $150 buffer, withdraw only above a $3k cushion): avg $4,843,
  median $226, 53% ever pay out.
- Funded 150K, v2 policy: avg $7,488 (2y), median $6,653, 62% pay out, 70% alive at 2 years.

## Ladder (best policy so far: v2 funded policy, 1 Combine at a time, move to 150K when cash allows)
| Scenario (5 years, $1,000 owner budget) | Ruin | First payout | $10k | $50k | $100k | $1M |
|---|---|---|---|---|---|---|
| Full period 2019-2026 | 46% | 76% @6.2 mo | 47% | 26% | 8% | 0% |
| 2019-2023 days only | 21% | 88% @4.7 mo | 75% | 61% | 39% | 0% |
| **2024-2026 days only** | **90%** | 50% @7.5 mo | 3% | 0% | 0% | 0% |
| Edge cut 25% | 66% | 63% | 22% | 5% | 0% | 0% |
| Edge cut 50% | 88% | 50% | 6% | 0% | 0% | 0% |
Original policy, $500 budget: ruin 94%, $10k 7%.

## NOISE edge by year ($/yr at 2 MNQ, no rules)
2019 $837 · 2020 $14,268 · 2021 $15,237 · 2022 $20,774 · 2023 $17,637 · 2024 $11,070 · 2025 $14,166 · 2026 YTD $6,604/yr pace

## Verdict (round 1)
- The plan is NOT validated yet. It works on 2019-2023 market behaviour but fails on 2024-2026 behaviour, and it is
  very sensitive to the edge size (25% weaker edge -> ruin 66%).
- $1M is not reached in 5 years in any scenario with Topstep alone (5-account cap, payout caps, edge size).
- Fixed along the way: payout cushion and cushion-based sizing (funded value x3.6), $150 buffer, 1 Combine at a time.
- Next: (1) strengthen the edge on recent data (strategy research, dev 2019-2023 / confirm 2024-2026),
  (2) bot changes for the funded phase (v2 sizing/buffer), (3) test other API-friendly firms / rules.
