from datetime import date, timedelta

from app.research.run_leveraged_nasdaq_weekly_stage_v1 import evaluate


def test_weekly_nav_signal_uses_prior_sessions_and_charges_turnover():
    first = date(2024, 12, 1)
    weekdays = [first + timedelta(days=i) for i in range(70)
                if (first + timedelta(days=i)).weekday() < 5]
    changes = {ticker: {day: 0.0 for day in weekdays}
               for ticker in ("SQQQ", "TQQQ")}
    start = date(2025, 1, 6)
    end = date(2025, 1, 13)
    changes["TQQQ"][date(2025, 1, 3)] = .2  # Friday signal before first Monday.
    changes["SQQQ"][date(2025, 1, 6)] = .5  # Monday close too late for Monday order.

    result = evaluate(weekdays, changes, start, end)

    assert [row["asset"] for row in result["daily_account_returns"]] == ["TQQQ"] * 5 + ["SQQQ"]
    assert (result["entries"], result["exits"]) == (2, 1)
    assert abs(result["observed_end"] - 100 * .9975 ** 3) < 1e-9
