# SMC fair-value-gap retest v1 — research plan (frozen before outcome)

Origin: the "Apex Algo Terminal" Smart Money Concepts engine written outside this repository on 2026-09-26. Its rules were never measured. This plan freezes the exact economic rule and costs before any price data for the evaluation windows is downloaded. No parameter below may be changed after the result is observed; any change is a new version.

Objective: test whether this rule can move a **$100 account toward the $500 waypoint** after costs on long-only spot crypto that Robinhood and Alpaca both list. It is a research proxy, not an executable Robinhood or Alpaca backtest.

## Data

Coinbase Exchange public 1-minute candles for BTC-USD, ETH-USD and SOL-USD. Unadjusted OHLCV. Minutes with no Coinbase candle are absent, not synthesized. Record the SHA-256 of the fetched candles and the count of missing minutes per coin.

- Warm-up: 2026-03-22 00:00 UTC to 2026-03-23 00:00 UTC (signals only, no trades).
- **Development window:** 2026-03-23 00:00 UTC → 2026-06-22 00:00 UTC.
- **Confirmation window (untouched):** 2026-06-22 00:00 UTC → 2026-09-22 00:00 UTC.

Each window starts a fresh $100 account.

## Signal (identical to Apex `signal_engine.find_setup`, bullish path only)

Evaluated at the close of every 1-minute bar using only the last 240 1-minute bars (current bar included):

1. Swing points are fractal pivots with 2 bars on each side, known only 2 bars after the pivot, and only when all 5 bars lie inside the 240-bar window.
2. **Sweep:** scanning back from the previous bar up to 30 bars (not before the window start), the most recent bar whose low is below the latest swing low known at that bar and whose close is above that level.
3. **MSS:** the latest swing high known at the sweep bar and located before it. The first bar after the sweep and before the current bar that closes above it.
4. **FVG:** the latest bullish three-candle gap (candle-1 high < candle-3 low) with candle 1 at or after the sweep, candle 3 no later than one bar after the MSS and before the current bar, and gap size ≥ 0.10 × ATR14 of the 240-bar window.
5. **First retest:** no bar between candle 3 and the current bar has a low at or below the gap top; the current bar's low is at or below the gap top and it closes above the gap bottom.
6. Each gap can signal at most once, and it is consumed even if a later filter rejects it.
7. **5-minute filter:** the direction of the last close through a confirmed swing (2-bar fractal) over the last 120 *completed* 5-minute buckets must be bullish; require at least 20 buckets.
8. Stop = sweep-bar low − 0.10 × ATR14. Target = nearest swing high above the close if it gives R:R ≥ 3 (capped at 8R), otherwise close + 3 × risk.

Short (bearish) setups are not traded: spot crypto on these venues is long-only.

## Execution model

- Entry at the **next bar's open** plus 0.05% slippage. Skip if that price is at or below the stop, at or above the target, or if the R:R recomputed from it is below 3.
- Skip if the stop distance is below 0.30% of the entry (Apex fee-drag filter).
- One open position across all three coins; when several coins signal on the same minute, take BTC, then ETH, then SOL.
- Size = 2% of account equity ÷ stop distance, capped at 95% of equity in notional. Minimum order $1.
- Exits are checked from the entry bar onward. When a bar touches both stop and target, assume the stop. Stop fills at the stop, or at the bar open if the open is already below the stop, less 0.05% slippage. Target fills at the target less 0.05% slippage.
- **Primary cost:** 0.25% fee on each entry and exit notional, on top of slippage. Reported sensitivities for the same trades: 0%, 0.10% and 0.75% fee per leg.
- Daily circuit breaker: if marked equity at any 1-minute close falls 5% below that UTC day's starting equity, close at that close and take no new entries for 24 hours.
- Any open position is closed at the last close of a window.
- The Claude pre-trade supervisor is **not** modeled; it can only veto trades, and historical model decisions cannot be reproduced.

## Reported measures

Per window and costs: ending equity, net return, trades, win rate, average R, profit factor, maximum drawdown on marked equity, whether and when $500 was reached, and daily net account returns including flat days. For the combined 182-day path, run the stage-distribution assessment: $100 start, $500 target, $50 floor, horizon equal to the observed days, five-day blocks, 10,000 paths, seed 20260926.

## Pass condition (all required at primary cost)

- Positive net return in **both** windows.
- Profit factor ≥ 1.2 and at least 30 trades in each window.
- Maximum drawdown ≤ 35% in each window.

Passing means only that the exact rule earns an exact-code paper lifecycle with Alpaca or Robinhood quotes, fills and exits. Failing is recorded and not tuned away.
