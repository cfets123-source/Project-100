# Veloikos Trading

Experimental autonomous-trading software under development. The repository now
contains Alpaca broker adapters and paper/live worker paths alongside research
code. The state of any deployed worker or broker account must be checked in
that environment; source code alone does not prove that a route is active.
Live execution is off by default in local configuration. The project objective
and the rules for stage-specific strategy work are in [Project 100 working
instructions](AGENTS.md). The account-equity ladder starts at **$100 → $500 →
$1,000** and continues to $1,000,000 within a year. This is an aggressive
research objective, not an expected or guaranteed return.

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

The backend suite includes simulated-data and broker-double tests; run it for
the current count rather than relying on an older README number. Tests alone
do not verify a live broker account. Some dependencies emit deprecation warnings.

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
