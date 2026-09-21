# Veloikos Trading

Experimental autonomous-trading software under development. Current behavior is
simulated; a persistent paper worker is available, but no real broker integration is present.
Live execution is disabled by default and must remain disabled while the remaining
safety and deployment work is completed. Capital milestones are aspirational,
not expected or guaranteed returns.

## Local tests

Use Python 3.12 or newer in an isolated environment. Python 3.9 is not
supported because the application uses modern type syntax:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest tests/ -q
```

The persistent-runtime validation run passed 153 tests. Tests use simulated data and broker
doubles, not real accounts. Some development dependencies emit deprecation warnings.

See [architecture](docs/ARCHITECTURE.md) and [safety limits](docs/THREAT_MODEL.md).
Never commit credentials, account databases, or private trading records.

Run the [persistent paper worker](docs/PAPER_RUNTIME.md) to replay simulated trades with restart recovery and a durable ledger.

See [performance and stage policy](docs/PERFORMANCE_AND_STAGES.md) and [container preparation](docs/DEPLOYMENT.md). Container execution has not yet been verified.

## Operations dashboard

Start the API with the same isolated environment used for tests, then open
`http://127.0.0.1:8000/dashboard`. The dashboard refreshes paper-runtime
health, cash, equity, positions, drawdown, closed-trade metrics, and recent
append-only actions every second. It is read-only and clearly labels simulated
data. Its Robinhood card stays disconnected until a real, authenticated
capability check succeeds; see [Robinhood onboarding](docs/ROBINHOOD_ONBOARDING.md).
