from datetime import date, timedelta
import copy

from app.research.monthly_etf_time_series_momentum_v3 import UNIVERSE
from app.strategies.monthly_etf_tsm_v3_paper import entry_order, entry_plan


def test_second_session_uses_completed_month_and_builds_whole_share_oto():
    days = []
    current = date(2023, 1, 2)
    while len(days) < 320:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    first = next(i for i in range(254, len(days) - 1)
                 if days[i][:7] != days[i - 1][:7])
    asof = days[first + 1]
    bars = {symbol: [] for symbol in UNIVERSE}
    for i, day in enumerate(days[:first + 1]):
        for symbol in UNIVERSE:
            price = 20 + i * .05 if symbol == "XLF" else 20
            bars[symbol].append({"timestamp": day, "open": price,
                                 "high": price, "low": price, "close": price})
    plan = entry_plan(bars, bars, raw_adjustment="raw", signal_adjustment="split",
                      asof_day=asof, session_days=days)
    assert plan.signal_day == days[first - 1]
    assert plan.ranked_symbols[0] == "XLF"
    order = entry_order(plan, asks={"XLF": 40.0}, tradable={"XLF"},
                        settled_cash=100.0)
    assert order.symbol == "XLF" and order.quantity == 2
    assert order.time_in_force == "gtc" and order.order_class == "oto"
    assert order.stop_loss_price == 36.0
    assert entry_plan(bars, bars, raw_adjustment="raw", signal_adjustment="split",
                      asof_day=days[first], session_days=days).reason == "not_second_trading_session"
    # A missing first-session IEX bar cannot shift the entry to day three.
    third = days[first + 2]
    assert entry_plan(bars, bars, raw_adjustment="raw", signal_adjustment="split",
                      asof_day=third,
                      session_days=days).reason == "not_second_trading_session"
    bars["XLE"][first - 30]["close"] /= 2
    assert entry_plan(bars, bars, raw_adjustment="raw", signal_adjustment="split",
                      asof_day=asof,
                      session_days=days).reason == "unresolved_signal_price_discontinuity"


def test_known_split_in_raw_bars_does_not_create_a_false_signal_crash():
    days = []
    current = date(2023, 1, 2)
    while len(days) < 320:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    first = next(i for i in range(254, len(days) - 1)
                 if days[i][:7] != days[i - 1][:7])
    asof = days[first + 1]
    signal = {symbol: [{"timestamp": day, "close": 20 + i * .05 if symbol == "XLF" else 20}
                       for i, day in enumerate(days[:first + 1])]
              for symbol in UNIVERSE}
    raw = copy.deepcopy(signal)
    for row in raw["XLE"][:200]:
        row["close"] *= 2
    plan = entry_plan(raw, signal, raw_adjustment="raw", signal_adjustment="split",
                      asof_day=asof, session_days=days)
    assert plan.reason == "eligible" and plan.ranked_symbols[0] == "XLF"
