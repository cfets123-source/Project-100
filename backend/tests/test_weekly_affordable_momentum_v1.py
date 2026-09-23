from datetime import date, timedelta

import pytest

from app.research.weekly_affordable_momentum_v1 import UNIVERSE, evaluate


def test_raw_price_boundary_and_whole_share_gap_stop():
    days = [(date(2024, 1, 1) + timedelta(days=n)).isoformat() for n in range(110)]
    data = {symbol: [{"timestamp": day, "open": 100, "high": 100,
                      "low": 100, "close": 100} for day in days]
            for symbol in UNIVERSE}
    with pytest.raises(ValueError, match="raw historical"):
        evaluate(data, adjustment="all")
    assert evaluate(data, adjustment="raw").trades == []


def test_partial_universe_is_rejected():
    with pytest.raises(ValueError, match="exact fixed universe"):
        evaluate({"BAC": []}, adjustment="raw")
