# Stage-by-stage strategy evaluation

Current mandate: start with $100, trade toward a first target in the $200–$500
range, sell, reconcile proceeds, and reinvest for the next milestone. The current
application default is $200. Continue through $1,000, $3,000, $5,000, $10,000,
$50,000, $100,000, $300,000, $500,000, and $1,000,000. Each stage can use a
separate strategy. No deadline was supplied in the current mandate.

This document supersedes the earlier one-year plan. Historical experiment plans
and results retain their original thresholds for reproducibility; they do not
set the current product mandate. Failing to reach $500 within a historical year
is not by itself evidence that a strategy loses money or is technically unusable.

Assess the next stage against executable account conditions: usable capital,
instrument and order affordability, broker permissions, entry and exit timing,
quantity rounding, costs, liquidity, and defined account loss limits. Freeze
candidate rules and acceptance criteria before evaluating untouched data. Report
net account return, drawdown, turnover, and milestone touches separately. Neither
a milestone touch nor a positive development result proves future profitability.

A strategy does not need to demonstrate the entire ladder, or a 5x historical
return, to satisfy an engineering release check. Strategy evidence, operational
readiness, and operator activation are distinct. Never clear a failed test merely
to reach deployment; never convert a development result into untouched evidence.

## Existing evidence and specific remaining work

- Daily pullback: the historical overnight evaluation differs from the worker's
  fractional DAY-stop/session-exit behavior. The same-day diagnostic lost 20.69%
  after modeled costs in 2025–September 2026. A matching evaluator must cover
  integer brackets as well as fractional exits. See
  [execution gate repair](../audit/EXECUTION_GATE_REPAIR.md).
- Whole-share overnight: its frozen confirmation failed. Preserve that result;
  changing the target does not change its return sequence.
- Monthly ETF V3: +6.19% in the inspected recent development window, with 19
  completed trades. This is a positive development result, not a failed strategy
  solely because it did not reach $500. It lacks untouched confirmation and a
  complete operational lifecycle. See [original result](MONTHLY_ETF_TSM_V3_RESULT.md).
- Weekly crypto and leveraged Nasdaq rotation: both lost money in their later
  inspected periods, independently of the original $500 milestone criterion.
  Preserve the original cost/data limitations and results.

Next engineering work must close a named execution or evidence defect. Do not
launch an endless series of parameter searches on already inspected periods.
A new strategy investigation requires a frozen hypothesis, appropriate data,
untouched confirmation, and a stopping rule before execution. No strategy is
currently represented as validated for live use by this document.

At a milestone, stop new entries, reconcile liquidation and outstanding orders,
verify available proceeds, then advance the stage. A balance crossing alone is
not a completed sale, and a new stage must not silently increase risk limits or
expand trading permissions.
