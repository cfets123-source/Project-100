# Prop-firm challenge simulator — fixed before running (2026-10-21)
Question: which strategy passes a futures prop challenge most often, and what does each funded account pay out?
Model account (Topstep-style 50K, typical of Lucid/Tradeify/Bulenox 50K): start $50,000, target +$3,000,
trailing max loss $2,000 (follows end-of-day high-water, locks at $50,000), daily loss limit $1,000,
breach checked on the day's worst price. Instrument: micro Nasdaq futures (MNQ) modelled from QQQ daily bars
(total-return removed: price only), notional exposure as a multiple of $50K. Cost $1.50/contract/side + 1 tick.
Fee assumption: $95 per attempt (one month); unpassed attempts after 30 trading days count as a second month.
Strategies (no tuning): S0 always long; S1 long only when QQQ > 200-day average; S2 long when 50d > 200d average.
Sizes: 0.5x, 1x, 2x notional. Start an attempt on every trading day 2011-01-03..2026-08-31.
Funded phase (after pass): same trailing $2,000; withdraw every time balance >= +$2,000 above the lock
(payout = $2,000 x 90%), until the trailing limit is hit or 250 trading days pass.
Report: pass rate, median days to pass, cost per pass, average total payout per funded account, net per attempt.
