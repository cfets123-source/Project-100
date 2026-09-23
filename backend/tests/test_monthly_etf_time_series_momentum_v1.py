import pytest

from app.research.monthly_etf_time_series_momentum_v1 import UNIVERSE, evaluate


def test_requires_raw_prices_and_exact_universe():
    with pytest.raises(ValueError, match="raw prices"):
        evaluate({s: [] for s in UNIVERSE}, adjustment="all",
                 start="2022-01-01", end="2023-01-01")
    with pytest.raises(ValueError, match="exact ETF universe"):
        evaluate({"XLF": []}, adjustment="raw",
                 start="2022-01-01", end="2023-01-01")
