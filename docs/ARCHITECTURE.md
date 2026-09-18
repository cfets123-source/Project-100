# Project 100 architecture

## Current implementation

Python/FastAPI shell, SQLite development storage, simulated broker and data
provider, deterministic risk evaluation, persisted operating state, entry intent
deduplication, risk reservations, reconciliation helpers, audit records and one
unvalidated test strategy.

Entry path:

Market data / strategy → signal schema → state/account checks → risk engine →
risk reservation → durable intent → mode/adapter checks → quote freshness →
final mutation policy → broker submission → audit.

Defensive path:

Protective-stop request → shared mutation policy (paper only) → order value
validation → simulated broker → audit; failure enters SAFE without clearing HALTED.

The complete paper entry-to-stop sequence is currently demonstrated in tests.
There is no continuously running trading process. The FastAPI routes remain
`/health`, `/system/state`, and `/config/risk`; health does not prove trading readiness.

## Safety regression pass

The original 73-test suite was independently reproduced at `2123a66`. The eight
subsequent failing safety checks are now regression tests. The expanded suite
contains 114 passing tests, including boundary cases for quote age and numeric
values, defensive mode/adapter restrictions, sticky halt, partial-order polling,
pre-submission reservation release and retention after unknown outcomes.

Gateway fixtures pin market-open behavior so authorization tests do not depend
on wall-clock time. Broker market-hour behavior remains separately tested.

## Next work

See [THREAT_MODEL.md](THREAT_MODEL.md) for remaining control limits. Production
work still requires a transaction-safe execution lifecycle, persistent paper
state and workers, authenticated controls, actual market-data and broker
integrations, strategy validation, capital stages, performance tracking and
cloud deployment. Do not enable real trading based on unit-test success.
