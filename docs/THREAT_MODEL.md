# Safety boundaries and remaining limits

This is a development-stage simulator, not an unattended live trading service.
`LIVE_TRADING_ENABLED` remains false by default. There are no real broker adapters.

## Enforced application behavior

- Entry proposals pass schema checks, deterministic risk evaluation, reservation,
  mode/adapter authorization, and a final state check after the data fetch.
- Entry and protective paths share `broker_authorization.mutation_allowed`.
  Defensive orders are currently supported only with a PaperBrokerAdapter in
  PAPER or SAFE and a paper configuration. SHADOW/OFF/RESEARCH/LIVE/HALTED cannot
  invoke that helper's broker mutations. Real protective orders remain blocked
  until account binding, verified position ownership and durable reconciliation
  have an implemented integration.
- SAFE cannot downgrade HALTED. An explicit reset is required to leave HALTED.
  The actor string is an internal API contract, not proof of authentication;
  an authenticated control API remains required before deployment.
- Quote freshness uses decision time, not just delivery latency. Finite numeric
  validation rejects NaN and infinities. Risk checks derive short restrictions
  from direction as well as legacy flags and enforce stop direction.
- Partial and accepted entry intents remain eligible for reconciliation.
- Proven pre-submission cancellation releases reserved risk. Unknown submission
  outcomes retain risk; they must not be treated as definitely canceled.

## Not guaranteed

Python policy functions do not isolate credentials or prevent arbitrary code
from calling a broker directly. Separate execution authority and broker account
binding are required for production. The final state check reduces races but is
not atomic with network submission; no cross-worker locking is implemented.

There is no persistent worker/supervisor, real data provider, account freshness
enforcement in the gateway, full position/exit ledger, strategy-performance
pipeline, capital-stage engine, or cloud deployment. Paper broker state is in
memory. Reservation release after closed positions and final reconciliation of
partially canceled orders require a complete lifecycle implementation.

Audit events use an ORM-level guard, not database-level immutability. State,
intent and audit writes are not one transaction. Unknown orders without broker
IDs have no automatic broker-side identity lookup. Protective orders do not yet
have durable intents, retry-safe submission, or outcome reconciliation.

The existing LIVE gateway mock tests explicitly override the default flag to
exercise failure paths. They do not establish permission or readiness for real
money. Passing tests demonstrate the covered cases only.
