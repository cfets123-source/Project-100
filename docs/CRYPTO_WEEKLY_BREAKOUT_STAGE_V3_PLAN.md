# Weekly crypto breakout V3: complete-history universe

V2's predeclared eight-coin universe could not run: Coinbase had 85 missing daily candles for PEPE and WIF at the start of the earlier comparison period. That is a **data-coverage failure**, not a strategy-return result. This V3 plan is frozen before calculating candidate returns. It retains V2's weekly rule, costs, dates, and account-level $100 → $500 → $1,000 waypoints, but uses the six coins that passed the full daily-coverage check: AVAX, BONK, BTC, DOGE, ETH, SOL. There is no parameter search or selection based on returns.

Every Monday UTC, rank the six coins by their previous completed day's 28-day close-to-close return. Hold 100% of the highest positive-return coin, or cash if none is positive, until the following Monday. Fill at the Monday UTC open and deduct 0.75% of equity per entry and exit leg. Evaluate the earlier 2024-09-22–2025-09-21 year and the subsequent 2025-09-22–2026-09-21 year separately. Record 365 daily net account returns in each year, including cash days, first $500/$1,000 touch, final account, drawdown, and descriptive five-day block resamples. No leverage, deposits, intraday stops, or post-result tuning.

Data source is Coinbase Exchange daily candles, a research proxy that does not establish actual Robinhood tradability, fill quality, or execution authority at those historical dates.
