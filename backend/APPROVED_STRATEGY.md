# Research candidate: execution path not approved

`defensive-etf-rotation-v1-vol-targeted` had a positive historical research
result, but it is **not approved for paper execution or live trading**. The
evaluator holds a position across sessions. The existing fractional-share
paper worker closes positions before its broker-side DAY stop expires, so it
would trade a different strategy. Its execution-matched promotion record must
remain failed until a matching broker path and complete paper lifecycle exist.

The $100 live account cannot buy a whole share of any ETF in this universe
within the current 50% position-value cap, so the execution design must also
resolve fractional overnight protection. Changing the holding period, stop,
or sizing requires a new strategy version and matching return assessment.
