# Execution gate repair — September 24, 2026

Status: deployed in the September 24 validation-repair web/observer image; 430 server tests passed. The trading worker remains stopped. See release/20260924-validation-repair/deployment-receipt.json.

The former final adapter gate permanently rejected four daily-pullback strategy
names. The gate now requires passing validation for the exact strategy plus
execution evidence attached to that same evaluation timestamp. Preflight uses
the identical check. A failed run still fails; rerunning an evaluator without
execution evidence revokes older evidence. Existing records are not upgraded.

The current worker's execution contract is
`alpaca-daily-pullback-mixed-quantity-day-stop-close45-bracket-v1`.
It includes BOTH fractional DAY-stop positions closed 45 minutes before the
broker's session close and the integer-quantity broker-bracket branch. The
contract must be explicitly supplied by an evaluator that actually models both
branches, sizing, fees, entry timing, and exit rules. Merely adding this string
to an overnight evaluator is not validation. Contract identifiers are versioned
research declarations, not automatic proof that an evaluator is correct.

Neither existing experiment qualifies: the overnight evaluator differs from the
worker, and the forced same-day diagnostic loses money and does not establish
passing untouched evidence for both quantity branches. No validation record,
account state, trading permission, or service activation was changed.

The new evidence table is created additively by initialize_schema. Deployments
using this code must initialize schema before running worker/preflight. The
earlier deployment receipt remains preserved; the new release has its own receipt.

Closure criteria: freeze a candidate and matching evaluator before confirmation;
record a passing, cost-adjusted untouched result with the matching execution
contract; confirm preflight and runtime agree. Operator activation is separate.
There is no requirement that the first-stage strategy demonstrate the entire
milestone ladder in one backtest.
