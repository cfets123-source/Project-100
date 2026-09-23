# Split-aware monthly ETF momentum v3: corrected development result

V3 rules were frozen in `54176cf` before this run. The same raw IEX bars from July 27, 2020 through September 22, 2026 were used for execution and affordability. Split-adjusted signal bars were derived from the issuer-confirmed 2-for-1 XLE and XLU splits effective December 5, 2025 by halving their pre-split prices. No other >30% raw close-to-close price discontinuity appeared in the 14-symbol cache. This local transformation is reproducible but still requires comparison with Alpaca's `adjustment=split` output before paper execution.

| Window, $100 initial cash | Completed trades | Return, 0.1% modeled roundtrip cost | Maximum drawdown | Return, 0.2% cost | Account breaker events |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2022–2024 | 30 | +13.32% | -22.40% | +11.77% | 1 |
| 2025–September 22, 2026 | 19 | +6.19% | -12.37% | +4.81% | 0 |

The corrected recent return is **6.19%**, versus **20.03%** in the invalid raw-signal V2 run. The recent path ended with an open marked position and no unaffordable entry month. Both windows were already inspected during earlier research, so these numbers are **development evidence**, not an untouched confirmation or a demonstrated route to the user's growth target.

The read-only V3 paper preflight checks the official trading calendar, exact raw and split-adjusted ETF bars, broker account flags, empty account state, fresh and affordable quotes, and a separately verified account-breaker state. It creates an OTO order *preview* only. A durable paper order worker, broker fill/stop/exit reconciliation, corporate-action handling for live holdings and stops, and a forward paper lifecycle remain outstanding. **No V3 broker order was submitted and no V3 live capital was enabled.**

Sources: [State Street split announcement](https://investors.statestreet.com/investor-news-events/press-releases/news-details/2025/State-Street-Investment-Management-Announces-Share-Splits-for-Five-Select-Sector-SPDR-ETFs/default.aspx); [Alpaca bar adjustment reference](https://docs.alpaca.markets/us/v1.4.2/reference/stockbars); [Alpaca market calendar](https://docs.alpaca.markets/us/v1.1/reference/getcalendar-1).
