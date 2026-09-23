# Risk-managed monthly ETF momentum v2: development evidence

The account-level breaker rule was frozen in `2de224b` before V2 was evaluated. It uses the same raw IEX ETF cache and historical periods already inspected for V1. This is **development evidence**, not an untouched confirmation.

| Period, $100 reset at start | Completed trades | Return at 0.1% modeled cost | Maximum drawdown | Return at 0.2% cost | Breaker events |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2022–2024 | 30 | +13.32% | -22.40% | +11.77% | 1 |
| 2025–September 22, 2026 | 19 | +20.03% | -12.31% | +18.64% | 0 |

The model's one breakout from a 20% equity decline blocked entries for 63 sessions. It improved the inspected development path while leaving the recent path unchanged. The recent period ended with an open marked position, and there were no unaffordable entry months. The model assumes one broker-side GTC stop for every whole-share position, a next-open circuit-breaker exit, and a settlement day before a new monthly entry. Actual stop acceptance, corporate-action handling, broker fill prices, exit cancellation races, cash settlement, and ledger reconciliation remain untested.

**Correction after data audit:** State Street's XLE and XLU both split 2-for-1 effective December 5, 2025. The raw-price series used for V2's 252-session momentum ranking halves across that date. The reported historical returns above are retained as the original run's audit record, **not** as valid strategy evidence. The paper planner now rejects unresolved raw-price discontinuities. A revised, frozen implementation must use split-adjusted prices for signals, raw prices for whole-share affordability, and split-aware holdings and stop accounting. It then needs a new test and broker paper lifecycle. V2 has no paper or live approval.

Source: [State Street split announcement](https://investors.statestreet.com/investor-news-events/press-releases/news-details/2025/State-Street-Investment-Management-Announces-Share-Splits-for-Five-Select-Sector-SPDR-ETFs/default.aspx); [Alpaca bar adjustments](https://docs.alpaca.markets/us/v1.4.2/reference/stockbars).
