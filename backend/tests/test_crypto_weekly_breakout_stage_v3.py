from datetime import date, timedelta

from app.research.run_crypto_weekly_breakout_stage_v2 import evaluate_window


def test_weekly_selection_uses_prior_close_and_charges_switch_both_legs():
    first = date(2024, 12, 1)
    data = {coin: {} for coin in ("BTC", "ETH")}
    for offset in range(60):
        day = first + timedelta(days=offset)
        data["BTC"][day] = (1.0, 1.0)
        data["ETH"][day] = (1.0, 1.0)
    data["ETH"][date(2025, 1, 5)] = (1.0, 2.0)  # Sunday signal for Monday.
    data["BTC"][date(2025, 1, 6)] = (1.0, 3.0)  # Too late for Jan 6 order.
    data["BTC"][date(2025, 1, 12)] = (1.0, 3.0)
    start, end = date(2025, 1, 6), date(2025, 1, 13)

    result = evaluate_window(data, start, end, ("BTC", "ETH"))

    assert [row["asset"] for row in result["daily_account_returns"]] == ["ETH"] * 7 + ["BTC"]
    assert (result["entries"], result["exits"]) == (2, 1)
    assert abs(result["observed_end"] - 100 * .9925 ** 3) < 1e-9
