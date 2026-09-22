# Intraday v3 research record — 2026-09-22

The 20-symbol, five-minute intraday candidate was changed from a one-position
model to a two-position model. Each position uses at most 40% of account
equity, with at most four entries per session and a 1.5% realized daily-loss
lockout. The simulator enters on the next bar, charges 0.1% round-trip cost,
assumes stop-first ordering when both exits are touched, penalizes gaps through
the stop, and closes remaining positions by the last observed session bar.

The 60-calendar-day Alpaca IEX historical run produced **108 simulated trades,
-8.69% modeled account return, and -8.82% maximum drawdown**. These data were
used while developing the candidate, so this is exploratory evidence, not an
untouched out-of-sample test. The persisted strategy validation record is
`passed=false`. No live worker uses this strategy. The three evaluator tests
and two emergency-exit guard tests passed in an isolated container.

Higher frequency alone did not improve this sample. Before any promotion, a
new frozen hypothesis needs independent holdout or forward data, paper order
fills and protective-stop evidence for its exact worker path, and a separate
readiness review. The current live worker's one-position restriction and the
shared paper/live kill-switch state also need deliberate design changes; a
research backtest cannot validate either broker behavior.
