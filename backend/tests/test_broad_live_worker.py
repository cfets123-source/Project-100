from app.runtime import alpaca_live_worker
from app.strategies.daily_trend_pullback import BroadDailyTrendPullback


def test_broad_worker_uses_its_own_validated_strategy_name(monkeypatch):
    seen = {}

    def fake_loader(db, cfg, strategy_name):
        seen["name"] = strategy_name
        return object()

    monkeypatch.setattr(alpaca_live_worker, "load_finally_authorized_adapter", fake_loader)
    assert alpaca_live_worker.start_live_worker(object(), object(), BroadDailyTrendPullback()) is not None
    assert seen["name"] == "daily-trend-pullback-broad-equity-etf-v1"
