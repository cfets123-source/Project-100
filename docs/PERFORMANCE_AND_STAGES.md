# Paper performance and capital stages

`GET /paper/performance` reports closed-trade metrics from the ledger, grouped by
strategy and filtered to `paper-1`. Values are explicitly labeled simulated.
Fees are included in ledger P&L. Missing/invalid closed-trade P&L fails validation;
it is never silently converted to a profitable result.

Metrics include sample size, win/loss count, win rate, realized P&L, expectancy,
profit factor and R multiples. The trade-Sharpe-like metric is mean R divided by
sample R standard deviation: it is unannualized and is not portfolio Sharpe.
Undefined ratios are null, not infinity or invented confidence estimates.

The paper runtime evaluates capital milestones after each committed replay event.
Defaults are $1,000 → $10,000 → $100,000 → $500,000 → $1,000,000. A policy may add
$300,000 as an intermediate checkpoint. Initial experimental capital remains $100.
There are no deadlines, forced trades, top-ups or automatic risk changes.

Graduation needs all of:

- Capital at or above the next milestone.
- At least 50 newly closed trades since the previous advancement/demotion.
- At least five loss observations, positive expectancy, profit factor >=1.2,
  and unannualized trade-Sharpe-like metric >=0.2.
- Observed portfolio drawdown <=10% and no unresolved orders/system incidents.

These are configurable engineering gates, not statistical proof of an edge.
The defaults have not been calibrated or backtested. Capital alone, one lucky
trade or all-winning data with undefined ratios cannot graduate. Each evaluation
can advance only one stage; a new sample is required for the following stage.
Trade IDs, rather than entry-time slicing, prevent late-closing trades from being
skipped or evidence from being reused. Capital retracement demotes the scoreboard.

Stage state persists in the database and all changes are audited. Policy changes
are rejected if they differ from the persisted policy; an explicit reviewed
migration is required. Graduation never writes execution permissions or risk
configuration. The runtime has no deposit operation, so deposits cannot be passed
through this implementation as trading returns. Real-account cash-flow handling
is not implemented and must precede a live version of this component.

`/paper/status` includes stage progress and reasons for holding the current stage.
