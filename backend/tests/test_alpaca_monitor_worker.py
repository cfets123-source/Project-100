from app.runtime.alpaca_monitor_worker import main
import pytest

def test_monitor_worker_rejects_unsafe_interval_before_broker_access():
    with pytest.raises(ValueError, match="interval"):
        main(["--database", "sqlite:///:memory:", "--symbols", "AAPL", "--interval", "1", "--once"])

def test_monitor_worker_rejects_empty_universe_before_broker_access():
    with pytest.raises(ValueError, match="symbol"):
        main(["--database", "sqlite:///:memory:", "--symbols", " , ", "--once"])
