# Project 100

Experimental autonomous-trading software under development. Current behavior is
simulated; no real broker integration or persistent autonomous service is present.
Live execution is disabled by default and must remain disabled while the remaining
safety and deployment work is completed. Capital milestones are aspirational,
not expected or guaranteed returns.

## Local tests

Use Python 3.12 in an isolated environment:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest tests/ -q
```

The safety-fix validation run passed 114 tests. Tests use simulated data and broker
doubles, not real accounts. Some development dependencies emit deprecation warnings.

See [architecture](docs/ARCHITECTURE.md) and [safety limits](docs/THREAT_MODEL.md).
Never commit credentials, account databases, or private trading records.
