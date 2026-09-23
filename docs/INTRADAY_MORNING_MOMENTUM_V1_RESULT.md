# Morning momentum v1: fixed-rule result

Commit `f067323` froze the rule and its pass criteria before the complete paginated Alpaca IEX five-minute dataset was evaluated. The dataset covers July 1, 2025 through June 30, 2026 for the exact 20-symbol universe. The planned simulation made 436 completed trades. Sixty-four symbol-days lacked at least one required opening, signal, entry, or scheduled exit bar and were excluded for that symbol.

| Window | Completed trades | Return after 0.1% round-trip cost | Maximum drawdown | Return at 0.2% cost |
| --- | ---: | ---: | ---: | ---: |
| July–December 2025 development diagnostic | 213 | -15.00% | -19.37% | -21.96% |
| January–June 2026 fixed confirmation | 223 | -4.40% | -9.76% | -12.56% |
| January–March 2026 | 108 | -4.85% | -8.83% | -8.88% |
| April–June 2026 | 115 | +0.47% | -6.16% | -4.05% |

The fixed confirmation fails the predeclared positive-return requirement. The increased trade count does not compensate for negative net account return. No parameter was retuned after reading these results, and this strategy is ineligible for paper or live promotion. The daily stock/ETF historical validator also does not model the fractional-share worker's required same-day exit before its DAY protective stop expires. That live route is disabled pending execution-matched validation.
