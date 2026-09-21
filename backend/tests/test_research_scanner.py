from app.markets.research_scanner import rank_research_candidates


def test_scanner_ranks_research_without_execution_authority():
    rows = rank_research_candidates([{"symbol": "SPY", "asset_class": "etf", "market_data_ready": True,
                                      "avg_dollar_volume": 1_000_001, "trend_score": .4, "momentum_score": .3}])
    assert rows[0]["status"] == "research_candidate"
    assert rows[0]["reason"] == "research_only"


def test_scanner_rejects_stale_market_data():
    rows = rank_research_candidates([{"symbol": "AAPL", "asset_class": "us_equity", "market_data_ready": False,
                                      "avg_dollar_volume": 2_000_000}])
    assert rows[0]["reason"] == "market_data_not_available"
