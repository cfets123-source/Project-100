# Persistent simulation worker

This runtime consumes **synthetic engineering replay events**, not a live market
feed. Its test strategy has no validated trading edge. No real broker adapter is
constructed and Live configuration is rejected. Do not infer returns from a replay.

## Run

From `backend/`, in the project's Python environment:

```sh
python -m app.runtime.worker --database /tmp/project100-demo.db run \
  --feed examples/paper-replay.jsonl --enable-paper --once
python -m app.runtime.worker --database /tmp/project100-demo.db status
```

Use a fresh database path for a new simulation. An existing paper session is
restored, never automatically refunded. Keep broker/account databases outside Git.

Remove `--once` to keep the process running and consume events as complete JSON
lines are appended to the file. The default poll interval is two seconds. Stop
with SIGINT/SIGTERM. A supervisor may restart the process with the same database
and file; omit `--enable-paper` on ordinary restarts. The process does not require
a browser or an open chat. It must still be hosted by an always-on machine to run
continuously; no cloud deployment is implied by this command.

Events need a stable `event_id`, monotonically increasing integer `sequence`, a
positive finite `prices` map, and optional `reference_prices` for the test strategy.
`market_open` is an explicit simulated session flag. Optional `source_timestamp`
is checked for freshness; when omitted, the synthetic prices are sampled at
processing time. This is not a real-data entitlement or exchange-calendar check.

Never modify already-processed input. Duplicate events with identical content are
ignored; reused IDs with different content and new events with older sequences
halt the runtime. Removing/changing the file prefix stops a running worker.

## Stop and reset

```sh
python -m app.runtime.worker --database /tmp/project100-demo.db halt --reason "operator stop"
python -m app.runtime.worker --database /tmp/project100-demo.db reset --confirm
```

Reset returns to OFF. Explicit paper enablement is required again. Starting a
worker cannot reset HALTED. Local CLI access is the authority boundary; there is
no remotely exposed mutation endpoint.

## Persistence and failure handling

SQLite `BEGIN IMMEDIATE` serializes each paper event, including duplicate worker
processes. Broker cash, positions, resting stops, orders, intents, reservations,
trade-close P&L, strategy statistics, audit records, and replay cursor commit in
one transaction. Failure before commit rolls the complete event back. The in-memory
broker object is discarded. Stable event identities prevent duplicate effects
after restart. These guarantees apply to the synthetic runtime only: a real
broker's external side effects cannot be rolled back this way.

The runtime refuses an existing legacy order database without runtime state.
Use a dedicated database; no silent migration or recovery of unrelated orders is
attempted. Cost settings are persisted and cannot silently change on restart.
Strategy statistics have `paper:`-prefixed keys. Fees are included in realized
P&L and planned risk sizing. Stops may gap, so planned risk is not maximum loss.

SQLite audit triggers reject UPDATE/DELETE even through raw SQL. A database
administrator can still drop the triggers or edit the file; this is not tamper-proof
external storage. The runtime creates additional tables in existing schemas; it
does not implement a general versioned production migration system.

## Health and known limits

The local FastAPI shell exposes `/paper/status` and `/ready`. Readiness requires
PAPER state, a healthy runtime, and both heartbeat and processed-data age <=30
seconds. A heartbeat alone cannot make a stale feed ready. These are read-only
development routes; keep the API bound to loopback until authentication is added.

The simulator fills supported entries immediately and supports stop/target exits.
It does not model realistic queue position, partial-fill liquidity, corporate
actions, exchange holidays or execution latency. Missing data pauses entries;
severe drawdown, inconsistent positions, or worker errors halt the system. A
missing protective order is treated as a serious anomaly. PostgreSQL runtime,
external orders, real market providers and unattended cloud operation remain
separate work. A finite replay naturally becomes not-ready after its feed stops.
