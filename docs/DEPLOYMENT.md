# Local container preparation — not a cloud deployment

The Dockerfile and `compose.paper.yml` are prepared for the **synthetic paper
worker only**. Docker was unavailable on the development host; these files were
syntax-inspected but no container image or deployment was executed/verified.
The application runtime is Python 3.12 (recorded in `.python-version`); do not
deploy it on Python 3.9.

On a machine with Docker Compose installed:

```sh
docker compose -f compose.paper.yml up --build
```

The worker consumes the mounted sample replay and then waits for appended events.
The API binds only to localhost at port 8000. A named volume preserves its SQLite
database across container restarts. The sample is finite, so `/ready` becomes 503
after the last event ages out; `/health` remains a process-liveness response.
Never relabel a finite replay as a continuously healthy live-market feed.

Both services run without root, with dropped Linux capabilities, a read-only
container filesystem (except data/temp mounts), and no broker credentials.
Automatic restart is limited to three failures. A halt cannot be reset by worker
startup. After an intentional reset, restart the worker to explicitly enable paper.

This is single-host SQLite configuration, not horizontally scalable production.
Before any cloud deployment: verify the container build and volume permissions,
exercise crash/restart and backup restoration, configure authenticated access,
TLS, external monitoring and off-host backups, choose an authorized host, and
review its costs. Real data, broker OAuth/MCP, PostgreSQL migrations, secrets
management and live-trading gates are separate uncompleted integrations.

## Tested local SQLite backup and restoration

From `backend/`:

```sh
python -m app.runtime.backup /path/paper.db /path/backups/paper-copy.db
python -m app.runtime.backup /path/backups/paper-copy.db /path/restored-paper.db
```

The copy uses SQLite's online backup API and verifies database integrity. It refuses
to overwrite an existing destination. Point the worker at the restored path only
after stopping the old worker and checking the recovered state. A restoration
test proved that an open simulated position and its protective stop survive the
copy and can close correctly in the restored database. Backup scheduling,
retention, encryption and off-host storage are not yet configured.
