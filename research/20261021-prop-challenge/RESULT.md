# Prop challenge simulator — first result (2026-10-21), daily-bar model
| Strategy | Size | Pass rate | Median days to pass | Avg payout per funded account | Expected net per $95 attempt |
|---|---|---|---|---|---|
| S0 always long | 1x | 24.2% | 20 | $763 | +$79 |
| S1 above 200-day | 1x | 22.0% | 23 | $840 | +$67 |
| S2 50d > 200d | 1x | 23.5% | 23 | $897 | +$86 |
| any | 2x | 15-17% | 5-6 | $475-609 | about $0 |
| any | 0.5x | 24-26% | 57-62 | ~$750 | about $0 |
- About 1 in 4 attempts passes; the rest lose the fee. Expected value is positive but small at 1x size; 2x passes faster but less often.
- Daily bars only; intraday rules (daily loss limit, intraday trailing) are approximated by the day's low. Intraday strategies need the 5-minute data on the server.

## Intraday result (2026-10-21) — NOISE on micro Nasdaq futures, flat daily, Alpaca SIP 5-min 2019-01-23..2026-09-30
Run on the Oracle server (chall_intraday.py appended to intraday_bt.py). Topstep-style 50K rules, $49/month fee.
| Size (x $50K notional) | Pass rate | Median days to pass | Fee cost per pass | Avg payout per funded account | Expected net per attempt |
|---|---|---|---|---|---|
| 1 | 26.1% | 58 | $646 | $1,175 | +$138 |
| **2** | **34.3%** | **31** | **$274** | **$1,074** | **+$274** |
| 3 | 31.0% | 15 | $206 | $811 | +$188 |
| 4 | 32.5% | 10 | $170 | $985 | +$265 |
- Chosen: size 2 (~2 micro Nasdaq contracts): highest pass rate and expected net. Published rules, not tuned; in-sample over the full period.
