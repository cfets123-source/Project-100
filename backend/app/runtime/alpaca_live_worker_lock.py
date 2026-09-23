"""Single-host process lock for live workers sharing one Alpaca account.

The production compose services mount the same /data volume. Keep this lock
for the entire worker lifetime so two live strategy processes cannot each see
an empty account and submit competing entries.
"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse


@contextmanager
def exclusive_live_worker(database_url: str):
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite" or not parsed.path.startswith("//"):
        raise RuntimeError("live worker lock requires a shared absolute SQLite volume")
    database_path = Path(parsed.path[1:])
    with (database_path.parent / ".alpaca-live-worker.lock").open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another Alpaca live worker owns this account") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
