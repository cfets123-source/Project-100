# Expanded two-position daily portfolio: exploratory result

The fixed two-position evaluator used 73,707 adjusted daily bars for the exact 79-symbol expanded equity/ETF universe, from January 2023 through September 22, 2026, with returns measured from January 2025. Alpaca pagination was fully consumed. Each scenario generated **210 completed trades** and reached two concurrent positions. The historical interval had already been inspected for the one-position strategy, so these are exploratory comparisons rather than untouched validation.

| Nominal risk per entry | Compounded portfolio return | Maximum drawdown |
| --- | ---: | ---: |
| 0.5% | -1.59% | -13.68% |
| 1.0% | -4.58% | -26.35% |
| 2.0% | -9.26% | -37.79% |

Allowing two simultaneous daily positions increased the trade count but made this unchanged selector lose money in the inspected interval. Neither higher nominal risk nor the lower-risk scenario produced a positive account return. This exact two-position proposal has no basis for a paper-to-live promotion. The separately validated **one-position** expanded strategy and its live activation review remain distinct.
