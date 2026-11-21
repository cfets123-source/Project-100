# 4-hour crypto test — fixed before running (2026-10-07)
Data: Binance.US klines BTCUSD/ETHUSD/SOLUSD, 4h and 1d, from listing (Sep 2019 / Sep 2020) to now.
Rules: the same frozen breakout + trend rules (multi_market_rules), 3 slots, 1/3 equity each, entry at next bar open,
stop checked before target, time/rule exit at next open. Cost 0.05% per side (0.02% taker + 0.03% slippage).
Variants:
  D  = daily bars (current live strategy), same data source, for a fair comparison
  4A = 4h bars, same % stop/target as daily, holding limit x6 bars (same calendar time)
  4B = 4h bars, stop/target scaled by sqrt(1/6)=0.41 (volatility-scaled), holding limit in bars unchanged
Periods: 2020-2022, 2023-Sep 2026, last 12 months.
Adopt a 4h variant only if it beats D in BOTH 2020-2022 and 2023-Sep 2026 after costs AND passes the stress gate
(P(touch $50 in 12 months) <= 10%, 20-day blocks; never below $50 from $100 in the 2021-22 crypto bear or March 2020).
