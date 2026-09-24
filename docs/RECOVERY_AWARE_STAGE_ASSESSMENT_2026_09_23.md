# Recovery-aware first-stage assessment — 2026-09-23

Target: $100 account equity to $500, measured after the costs already included in each recorded daily return. Idle days remain in the path. A losing day or drawdown is measured, not used as an automatic rejection. The path continues after any target touch so a subsequent loss would remain visible.

| Recorded rule and window | End equity from $100 | First $500 day | Worst drawdown | Longest underwater stretch | Gain required to regain prior peak at end |
| --- | ---: | ---: | ---: | ---: | ---: |
| Crypto weekly breakout, 2024-09-22–2025-09-21 | $186.18 | None | 64.5% | 287 days | 65.9% |
| Crypto weekly breakout, 2025-09-22–2026-09-21 | $24.39 | None | 78.6% | 364 days | 317.1% |
| Leveraged Nasdaq weekly, 2024-09-23–2025-09-19 | $115.77 | None | 50.8% | 114 trading days | 20.9% |
| Leveraged Nasdaq weekly, 2025-09-22–2026-09-21 | $84.66 | None | 35.5% | 134 trading days | 52.2% |

Source paths: `CRYPTO_WEEKLY_BREAKOUT_STAGE_V3_DAILY_RETURNS.json` and `LEVERAGED_NASDAQ_WEEKLY_STAGE_V1_DAILY_RETURNS.json`. Calculations use `assess_recovery_path` in `backend/app/research/recovery_path.py`. The second crypto window crossed a $25 illustrative account floor. These are observed model windows, not a probability of future success or a verdict on all possible rules. The missing $500 milestone is the specific gap to address before treating either exact rule as a first-stage candidate.

Broker access is a separate question: the connected Robinhood Agentic account currently reports Level 2 options, and the Alpaca live account reports Level 3. Robinhood options quotes can now be inspected read-only with contract multiplier, ask cost, spread, and age; historical execution quotes, an options exit/reconciliation path, and funded broker permission are still needed before an exact options rule can use live capital.
