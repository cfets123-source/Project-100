from app.research.monthly_etf_time_series_momentum_v3 import apply_split


def test_split_preserves_position_value_and_stop_basis():
    before = ("XLE", 2, 90.0, "2025-12-02")
    after = apply_split(before, 2)
    assert after == ("XLE", 4, 45.0, "2025-12-02")
    assert before[1] * before[2] == after[1] * after[2]
    assert before[2] * .90 / 2 == after[2] * .90
