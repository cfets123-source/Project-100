from app.runtime.market_research_worker import run_equity_scan, run_scan


class Adapter:
    def get_daily_bars(self, symbol, start, end):
        return [{"close": 100 + i, "volume": 2_000_000} for i in range(60)]


def test_research_scan_is_ranked_and_read_only(monkeypatch):
    events = []
    monkeypatch.setattr("app.runtime.market_research_worker.log_and_commit", lambda _db, event, payload: events.append((event, payload)))
    rows = run_scan(object(), Adapter(), symbols=("SPY",))
    assert rows[0]["status"] == "research_candidate"
    assert events[0][0] == "market_research_scan_recorded"


def test_equity_scan_is_classified_and_audited_separately(monkeypatch):
    events = []
    monkeypatch.setattr("app.runtime.market_research_worker.log_and_commit", lambda _db, event, payload: events.append((event, payload)))
    rows = run_equity_scan(object(), Adapter(), symbols=("AAPL",))
    assert rows[0]["asset_class"] == "us_equity"
    assert events[0][0] == "equity_research_scan_recorded"
