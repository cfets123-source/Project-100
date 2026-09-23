# End-of-day reversal v1: failed confirmation

Commit `5e86f22` froze the 20-symbol, two-position, same-session rule and pass criteria before the separate 2023–2024 confirmation bars were fetched. The read-only Alpaca IEX five-minute fetch was paginated for every symbol. No order was submitted and no paper or live route uses this candidate.

| Window | Simulated trades | Modeled account return after 0.1% round-trip cost | Maximum drawdown |
| --- | ---: | ---: | ---: |
| July 2025–June 2026 exploratory development | 372 | -8.97% | -12.34% |
| January–December 2023 fixed confirmation | 303 | -10.24% | -10.78% |
| January–December 2024 fixed confirmation | 340 | -15.28% | -15.43% |
| 2023–2024 combined confirmation | 643 | -23.96% | -24.42% |

The confirmation contained 643 simulated trades across 496 sessions. Sixty-six trades hit the stop, one reached the target, and 576 exited at the planned session close. There were 343 missing required symbol-bars across the full 20-name universe; those symbol-days were excluded. The combined return was -1.65% even with zero transaction cost and -41.22% at the predeclared 0.2% cost stress. Both confirmation years were negative. This fails the positive-return, drawdown, and cost-stress gates. More frequent trades did not establish an edge, so this exact version is ineligible for an execution worker or paper/live promotion.

These results are modeled with five-minute IEX bars rather than exact broker quotes and fills. The rule was evaluated as frozen; no thresholds were retuned after the confirmation result.
