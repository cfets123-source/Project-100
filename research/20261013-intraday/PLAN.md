# Intraday (day-trading) test — fixed before running (2026-10-13)

Why now: FINRA retired the Pattern Day Trader rule on 2026-06-04 and Alpaca lifted it, so the $100 account may
day trade. Under $2,000 there is no intraday margin, so every candidate uses cash only (100% of equity, no
borrowing). Leverage comes only from 3x ETFs: TQQQ for long, SQQQ for short (no short selling needed).

## Data
Alpaca 5-minute bars, SIP feed (IEX if SIP is refused), split/dividend adjusted, regular session 9:30–16:00 ET.
QQQ (signal), TQQQ and SQQQ (execution), 2019-01-01 to 2026-09-30. Downloaded once by `fetch.py` on the server
with the existing read-only Alpaca credential. No paid data.

## Candidates (published rules, not tuned here)
**ORB5 — 5-minute opening-range breakout** (Zarattini & Aziz 2023, "Can Day Trading Really Be Profitable?").
- Opening bar = QQQ 9:30–9:35. Up bar → buy TQQQ at the 9:35 open; down bar → buy SQQQ. Flat bar → no trade.
- Stop: QQQ trades through the other end of the opening bar. Target: 10× that distance (R) in QQQ.
- Otherwise sell at the 15:55 bar close. One trade per day.

**NOISE — noise-area intraday momentum** (Zarattini, Aziz & Barbon 2024, "Beat the Market").
- σ(t) = average over the previous 14 days of |QQQ price at time t / that day's open − 1|.
- Upper = max(open, previous close) × (1 + σ); Lower = min(open, previous close) × (1 − σ).
- Checks at :00 and :30 from 10:00 to 15:30. Above Upper → buy TQQQ next bar; below Lower → buy SQQQ next bar.
- Exit (next bar open) when a check finds QQQ back below max(Upper, VWAP) for longs / above min(Lower, VWAP) for shorts.
- Everything sold at the 15:55 bar close.

Execution model: 3x ETF fills at its own 5-minute bar prices. Stop fills inside a bar use the ETF bar open moved
3× the QQQ distance to the stop (the bar open if QQQ gapped past it). Cost 0.03% per side (spread + slippage;
Alpaca charges no commission). Every result is also reported at 0.06% per side.

## Periods
Development 2019-01-02 – 2023-12-29. Confirmation (untouched) 2024-01-02 – 2026-09-30.

## Benchmark: the live allocator, same windows, from $100 (rot_curve.py, weekly swap)
Development $331 (max drawdown 53%). Confirmation $217 (max drawdown 39%).

## Acceptance rule (per candidate, at 0.03% cost)
Pass only if ALL hold:
1. Ends above $100 in both periods.
2. Ends above the allocator in both periods ($331 and $217).
3. Still ends above $100 in both periods at 0.06% cost.
4. Stress gate (same as the allocator): P(touching $50 within 12 months) ≤ 10% in a 4,000-path bootstrap with
   20-day blocks of the strategy's daily returns, AND never below $50 from $100 in the COVID crash (2020-02-19 to
   2020-04-30) or in the 2022 bear market.

If both pass, the one with the higher confirmation result goes forward. A pass leads to paper trading first
(at least 10 sessions, fills compared with the model), then a live decision by the owner. If neither passes, the
result is reported as FAIL and no variants are tried on the same data; the next step is to revisit the strategy.
