# Multi-market core test — fixed before running (2026-10-15)

Problem: the live allocator keeps 50% of the account permanently in TQQQ (3x Nasdaq). Week of 10-12 the
Nasdaq-100 fell 3.8%, TQQQ 11.2%, and most of the account's loss came from that one holding.

Change tested: ONLY the 50% core. Satellites (5 slots, breakout/trend signals, weekly swap) stay exactly as live.

## Core candidates (weekly, Monday open; signal = 126-day total return at the prior close)
Markets: US large tech (QQQ), US large (SPY), US small (IWM), developed intl (EFA), emerging (EEM),
long Treasuries (TLT), gold (GLD), commodities (DBC). Safety asset: short Treasuries (SHY).
- **MC1 (unleveraged):** hold the top 2 markets by 126-day return, 25% of equity each, buying the ETF itself.
- **MC2 (leveraged where a fund exists):** same ranking on the same signal ETFs, but buy TQQQ for QQQ, UPRO for SPY,
  TNA for IWM, TMF for TLT (EFA, EEM, GLD, DBC unleveraged — no liquid leveraged fund in our data).
- Absolute filter (both): a market whose 126-day return is not above SHY's goes to SHY instead.
- A holding is only traded when it drops out of the top 2. No stops on the core (the weekly rank is the exit).
Cost 0.05% per side. Crypto is not in the core (Alpaca crypto unavailable in Florida; crypto runs on Binance.US).

## Benchmark: live allocator (rot_curve.py, weekly swap), from $100
Dev 2019-01-02..2023-12-29: $331, max DD 53%. Conf 2024-01-02..2026-09-30: $217, max DD 39%.

## Acceptance (per candidate), must hold in BOTH periods
1. Ends >= the allocator, OR ends >= 85% of the allocator with a max drawdown at least 10 points smaller.
2. Stress gate: P(touch $50 within 12 months) <= 10% (4,000 paths, 20-day blocks, daily returns 2019–Sep 2026)
   and never below $50 from $100 in COVID (2020-02-19..2020-04-30) or 2022.
If both pass, the one with the higher confirmation result goes forward (paper, then owner decision).
If neither passes: FAIL, the TQQQ core stays, no variants on this data.
