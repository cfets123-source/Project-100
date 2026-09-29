# September 24 test and market-data evidence

## Current checkout software tests

The current checkout at `d00193e`, including existing uncommitted research files, was copied into a temporary Docker build context on the Project 100 host. The isolated image was run without network access:

```text
python -m pytest -q --tb=short -p no:cacheprovider --disable-warnings tests
383 passed, 1071 warnings in 26.79s
```

This is software regression evidence. It does not measure strategy returns or authorize a live order. The deployed `project-100-robinhood-option-quotes:latest` image still has an older embedded test snapshot; its full suite yielded 287 passed and six failed. Those failures concerned old paper-worker test mocks, an old protective-error expectation, and old crypto-account fixtures. The current-checkout image passed those same suites. No production service or broker order was changed by these test runs.

## Robinhood option-history coverage audit

Read-only Agentic historical requests asked for five-minute regular-session OHLC bars from August 20 through September 18, 2026, for SPY September 18 765 call and put and earlier September 11 and September 4 765 calls. Synthetic gap fills (`interpolated=true`) were excluded:

| Contract | Returned bars | Non-interpolated bars | First non-interpolated bar |
| --- | ---: | ---: | --- |
| SPY Sep 18 765 call | 1,638 | 390 | Sep 14, 9:30 a.m. ET |
| SPY Sep 18 765 put | 1,638 | 390 | Sep 14, 9:30 a.m. ET |
| SPY Sep 11 765 call | 1,638 | 0 | None |
| SPY Sep 4 765 call | 1,638 | 0 | None |

The current October 2 SPY contracts likewise produced real bars only for recent sessions. Historical option OHLC lacks bid, ask, volume, and executable fill prices. The available series therefore cannot support a multi-month, execution-matched untouched test for a new first-stage options strategy. The read-only forward bid/ask collector can accumulate future quote evidence, but its observations must be tied to a frozen strategy and modeled with spread, fees, slippage, expiry, and broker-side exit behavior before promotion. No option return or account milestone is claimed from this audit.

## Live gate

The last read-only production preflight was blocked by `strategy_execution_horizon_mismatch_fractional_day_stop` and `system is not in live state`. The expanded daily pullback diagnostic was negative over 423 evaluable trades (see [session-matched result](SESSION_MATCHED_DAILY_PULLBACK_2025_2026.md)). Passing the software suite does not clear either gate or provide a tested replacement strategy.
