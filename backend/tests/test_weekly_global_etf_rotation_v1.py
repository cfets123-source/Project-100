import pytest

from app.research.weekly_global_etf_rotation_v1 import UNIVERSE, evaluate


def test_requires_exact_universe_and_raw_prices():
    with pytest.raises(ValueError, match="raw prices"):
        evaluate({symbol: [] for symbol in UNIVERSE}, adjustment="all")
    with pytest.raises(ValueError, match="exact ETF universe"):
        evaluate({"XLF": []}, adjustment="raw")


def test_empty_history_does_not_invent_trades():
    result = evaluate({symbol: [] for symbol in UNIVERSE}, adjustment="raw")
    assert result.trades == [] and result.equity == []
