from app.research.whole_share_breakout_stage_v1 import simulate


def test_idle_days_and_whole_share_affordability_are_counted():
    bars = [
        {"timestamp": f"2026-01-{day:02d}T00:00:00Z", "open": 120, "high": 121,
         "low": 119, "close": 120, "volume": 100}
        for day in range(1, 24)
    ]
    bars[20]["close"] = 122
    bars[20]["high"] = 123
    bars[20]["volume"] = 200
    result = simulate({"F": bars, "SOFI": bars}, "2026-01-01", "2026-01-23")
    assert result["trades"] == 0
    assert result["final_equity"] == 100
    assert len(result["daily_equity"]) == 23


def test_gap_below_stop_uses_open_price():
    bars = [
        {"timestamp": f"2026-01-{day:02d}T00:00:00Z", "open": 10, "high": 11,
         "low": 9.9, "close": 10, "volume": 100}
        for day in range(1, 24)
    ]
    bars[20].update({"close": 12, "high": 12, "volume": 200})
    bars[21].update({"open": 12, "high": 12.2, "low": 11.9, "close": 12})
    bars[22].update({"open": 10, "high": 10.5, "low": 9.8, "close": 10})
    result = simulate({"F": bars, "SOFI": bars}, "2026-01-01", "2026-01-23")
    assert result["trades"] == 1
    assert result["trade_log"][0]["reason"] == "stop_gap"
    assert result["final_equity"] < 100
