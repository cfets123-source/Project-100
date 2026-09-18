# Release gate — Project 100

This is the single truth source for whether the service can progress toward a
funded, live account. A checked item requires evidence, not a claim.

## Complete locally

- [x] Paper-only default configuration and independent live-execution lock
- [x] Deterministic risk, freshness, stop, kill-switch, audit, reconciliation,
  durable replay, stage, performance, backup, and dashboard components
- [x] Read-only broker verification contract that cannot call a trading method
- [x] Python 3.12 CI workflow for the full simulated-runtime test suite

## Required before funding for this application

- [ ] A real Robinhood MCP transport adapter has been implemented and has passed
  a read-only capability check against the dedicated Agentic account.
- [ ] The application can display the verified account's actual cash, positions,
  open orders, data freshness, and broker health on its dashboard.
- [ ] A real, licensed market-data source is integrated and tested through
  shadow mode; synthetic replay data is not sufficient.
- [ ] A shadow run has gathered enough reconciled evidence to define an explicit
  promotion policy. No fixed number of trades is assumed to establish safety or
  performance.
- [ ] A cloud host, TLS, authenticated dashboard access, secret store, external
  monitoring, off-host encrypted backups, and rollback drill are configured and
  verified.
- [ ] The container image is built and exercised on the chosen host.

## Required before any live execution

- [ ] The prior funding gates are complete.
- [ ] The selected Agentic account and its buying power have passed a fresh,
  read-only reconciliation.
- [ ] An explicit, separate live-enable decision has been recorded. Funding an
  account does not enable live execution.

The live-execution lock remains false until every relevant gate has evidence.
