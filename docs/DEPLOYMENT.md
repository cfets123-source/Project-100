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

## Single-server paper dashboard

`compose.host.paper.yml` is a repeatable, password-protected deployment for a
single server. It remains paper-only and binds the API to the server loopback
address. Copy `.env.host.example` to a host-only `.env.host` file, replace both
secrets, and start it with:

```sh
docker compose -f compose.host.paper.yml up --build -d
```

Do not open port 8000 directly to the internet. Until a domain, TLS reverse
proxy, and firewall policy are completed, reach it through an authenticated SSH
tunnel. A public HTTPS address is also required before configuring Robinhood's
application OAuth redirect URL.

## Required secret configuration for a hosted dashboard

Before setting `APP_ENV=production`, set these values in the chosen host's
secret manager. Do not put any of them in the repository, Docker image, or a
committed `.env` file.

- `DASHBOARD_USERNAME` and a strong `DASHBOARD_PASSWORD` protect `/dashboard`
  and its operational data APIs with browser sign-in.
- `BROKER_OAUTH_REDIRECT_URL` must be the deployment's HTTPS callback URL.
- `BROKER_TOKEN_ENCRYPTION_KEY` must be a unique Fernet key stored only by the
  host. Generate it with `Fernet.generate_key()` from the `cryptography`
  package; rotating it disconnects existing broker sessions until reauthorized.

Production startup refuses an empty dashboard password. The separate broker
OAuth callback remains public because Robinhood must redirect to it; its
short-lived PKCE state validates the return and it does not expose credentials.

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
