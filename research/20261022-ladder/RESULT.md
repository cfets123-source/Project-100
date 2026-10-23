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

# Round 2 (2026-10-22): strategy upgrade + other firms
## Strategy variants (score = expected profit per 50K Topstep Combine attempt; DEV 2019-2023 / CONF 2024-2026)
| Variant | DEV | CONF |
|---|---|---|
| Current bot (30-min checks) | +$792 | −$61 |
| Hourly checks | +$1,105 | +$394 |
| Hourly + volatility sizing (1.0% target, whole contracts) | **+$1,370** | **+$376** |
| Hourly + vol sizing 1.3% | +$994 | +$765 |
| Band k 0.8 / 1.2 / 1.5 (30-min) | +$962 / +$818 / +$454 | −$13 / −$100 / −$58 |
| Costs x3 (hourly) | +$519 | +$187 |
Chosen by DEV: hourly + vol sizing 1.0%. Stays positive on unseen 2024-2026 data.
Ladder with it (5y, $1k budget): full-period ruin 48%; 2024-2026-only ruin 82% (was 90%). Signal alone does not fix it.

## Structural finding
Topstep's $2k trailing cushion, 5-account cap, payout caps and $49/mo + $149 activation dominate the outcome.
Scaling the way multi-account traders do needs more firms and cheap evaluations. Automation-friendly futures firms
(Oct 2026, to verify per rulebook): FTMO Futures (VPS allowed, 3 accts), FundedNext Futures (VPS allowed, 5),
Lucid (5), Tradeify (5, video check), Bulenox (Rithmic API/NinjaTrader, 5-11, EOD plans, evals as low as ~$16 on
sale), MyFundedFutures (own strategy, no copy trading). Apex banned automation (Mar 2026); Phidias bans full automation.
Route for non-Topstep firms: signal -> TradingView/relay (TradersPost/PickMyTrade) or NinjaTrader -> Tradovate/Rithmic.
Next: model each firm's exact rules and sale prices on 2024-2026 data, then build the relay integration.

# Round 3 (2026-10-22): firm ranking (50K plans, bot signal = hourly + vol sizing, funded policy v2, 1-year funded horizon)
Rules from each firm's help center (Bulenox, FundedNext, Lucid, Tradeify, FTMO Futures, TradeDay, MFFU; read 10-22).
Tradeify excluded: its rules forbid running the same bot at multiple firms. Apex/Phidias ban automation.
| Plan | EV per attempt 2024-26 | 2019-23 | Pass 2024-26 | Cost per attempt | Cost per pass |
|---|---|---|---|---|---|
| Lucid 50K Flex (one-time ~$88 w/ code, no activation) | **+$340** | +$995 | 36% | $88 | $244 |
| Topstep 50K Standard ($49/mo + $149 act.) | +$302 | +$1,121 | 38% | $75 | $348 |
| MFFU 50K Rapid EOD (one-time ~$135) | +$278 | +$981 | 36% | $135 | $374 |
| FTMO 50K Growth ($119/mo) | +$257 | +$916 | 36% | $195 | $541 |
| Bulenox 50K Qualification EOD ($175 + $148 act.) | +$117 | +$1,256 | 47% | $175 | $522 |
| FundedNext 50K Flex | +$89 | +$621 | 20% | $80 | $393 |
| TradeDay 50K Fast Pass | +$78 | +$574 | 36% | $138 | $384 |
| FundedNext 50K Rapid Pro | +$33 | +$629 | 40% | $170 | $425 |
Every plan is positive in both periods. Expansion order: Lucid Flex, then MFFU Rapid EOD, then FTMO (3 accounts).
Cap with Topstep 5 + Lucid 5 + MFFU 5 + FTMO 3 = 18 funded accounts (all trade the same signal).

# Round 4 (2026-10-22 night): aggressive "replace what fails" policy (Alex-style)
Metric: steady-state net income per account slot per month = (payouts - evaluation/activation costs) / months per
cycle (evaluation + funded life, failures replaced). Funded: fixed contracts, withdraw as soon as allowed above a cushion.
| Plan | Protective (2 eval / 1 funded) 2024-26 | Best aggressive 2024-26 | all years | settings (eval/funded contracts) |
|---|---|---|---|---|
| MFFU 50K Rapid EOD | $180 | **$736** | $340-688 | 4/3 (2/2 best all-years) |
| Lucid 50K Flex | $208 | **$609** | $537 | 4/3, $1k cushion |
| Topstep 50K | $196 | **$491** | $507 | 4/2, $1k cushion |
| Bulenox 50K | $61 | $218 | $231 | 4/2 |
| MFFU 150K Rapid EOD | - | **$960** | $884 | 4/6 |
| Lucid 150K Flex | - | $570 | $615-1,016 | 9/3 or 9/6 |
| Topstep 150K | - | $544 | $847 | 4/6 |
Aggressive sizing with cheap one-time evaluations earns 2.5-4x more per slot than the protective policy.
Full stack estimate (Topstep 5 + Lucid 5 + MFFU 3-5 + FTMO 3 + others): ~20-30 slots x ~$500-900 = ~$10k-25k/month
on 2024-26 behaviour, before the ramp-up period. Next: multi-firm ladder simulation with this policy and staged cash.
