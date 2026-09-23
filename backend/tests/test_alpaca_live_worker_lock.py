import pytest

from app.runtime.alpaca_live_worker_lock import exclusive_live_worker


def test_two_live_workers_cannot_share_one_account_database(tmp_path):
    database = f"sqlite:////{str(tmp_path).lstrip('/')}/paper.db"
    with exclusive_live_worker(database):
        with pytest.raises(RuntimeError, match="another Alpaca live worker"):
            with exclusive_live_worker(database):
                pass
    with exclusive_live_worker(database):
        pass


def test_live_worker_requires_shared_absolute_sqlite_path():
    with pytest.raises(RuntimeError, match="shared absolute SQLite"):
        with exclusive_live_worker("sqlite:///local.db"):
            pass
