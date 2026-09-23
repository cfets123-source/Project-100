# Expanded daily pullback: session-matched diagnostic

On September 23, 2026, the same 79-symbol daily pullback selector was evaluated with next-session entry, a 3% stop, a 6% target, and a forced exit at the start of the 15:15 Eastern five-minute bar. That exit approximates what the live fractional-share worker must do before its broker-side DAY stop expires. Position exposure was one-third of account equity, matching a 1% account risk budget divided by the 3% stop, with no leverage. The diagnostic used Alpaca adjusted IEX daily bars for signal selection and paginated adjusted IEX five-minute bars for the selected symbol and entry day. It modeled the 9:30 bar open as entry, adverse stop priority if a bar touched both thresholds, and a 0.1% round-trip cost on traded notional. The exact 79-name selector generated 431 entry days from January 2025 through September 22, 2026; eight sessions lacked the required entry or exit bar and were excluded.

| Period | Evaluable trades | Compounded modeled account return | Maximum drawdown | Win rate |
| --- | ---: | ---: | ---: | ---: |
| 2025 | 243 | -15.69% | -18.10% | 44.86% |
| 2026 through September 22 | 180 | -5.94% | -18.42% | 42.78% |
| Combined | 423 | -20.69% | -23.86% | 43.97% |

The combined return was -8.68% with no transaction-cost deduction and -31.13% at a 0.2% cost stress. Of 423 evaluable trades, 86 hit the stop, 15 hit the target, and 322 exited at session close. The 6% target that often works in an overnight-hold simulation was rarely reached within one session.

This is a diagnostic, not a live validation record. Five-minute IEX bars cannot reproduce the exact broker quote, spread, order timing, partial fills, or stop cancellation. The 2025–2026 period had already been inspected during related research, so it is not pristine untouched confirmation. Even with those favorable limitations, the modeled return is negative before costs. The historical overnight pass must not authorize the fractional same-day worker. The live adapter and expanded preflight now reject that version until a separately named, execution-matched strategy has positive independent validation and its own paper broker lifecycle.

The production host was verified flat in paper and live, with prior exits and risk reservations reconciled. All live-worker flags are off, the app state is shadow, and the live workers are stopped. The paper research worker and read-only live reconciliation service remain running.
