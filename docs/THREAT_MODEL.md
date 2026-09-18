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

The standalone paper runtime persists its simulated broker state, handles full-fill
entry/exit accounting and reservation release, and serializes events with a SQLite
write lock. It is not a real-market service or a cloud deployment. The general
non-runtime gateway still lacks transaction-safe external-order lifecycle, account
freshness enforcement, partial-cancel reconciliation, and cross-worker protection.
Capital-stage evaluation and real data/broker integrations remain outstanding.

Outside the paper runtime, audit events use an ORM-level guard. The SQLite paper
runtime also installs UPDATE/DELETE-blocking triggers. State,
intent and audit writes are not one transaction. Unknown orders without broker
IDs have no automatic broker-side identity lookup. Protective orders do not yet
have durable intents, retry-safe submission, or outcome reconciliation.

The existing LIVE gateway mock tests explicitly override the default flag to
exercise failure paths. They do not establish permission or readiness for real
money. Passing tests demonstrate the covered cases only.

See [PAPER_RUNTIME.md](PAPER_RUNTIME.md) for the atomic, simulation-only worker guarantees. They do not extend to external broker side effects.
