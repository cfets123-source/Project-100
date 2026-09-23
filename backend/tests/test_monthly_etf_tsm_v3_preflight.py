from datetime import date, timedelta

from app.brokers.base import Quote
from app.research.monthly_etf_time_series_momentum_v3 import UNIVERSE
from app.strategies.monthly_etf_tsm_v3_preflight import check


def _fixture():
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
    return days, asof, bars


def test_read_only_preflight_checks_account_and_quotes_before_preview():
    days, asof, bars = _fixture()

    class Paper:
        paper = True
        allow_order_submission = False
        orders = []
        quote_age = 1

        def get_market_clock(self): return {"is_open": True}
        def get_account_capabilities(self): return {"status": "ACTIVE"}
        def get_positions(self): return []
        def get_orders(self): return self.orders
        def get_market_calendar(self, start, end):
            return [{"date": day} for day in days if start <= day <= end]
        def get_daily_bars_many(self, symbols, start, end, *, adjustment):
            assert adjustment in {"raw", "split"} and set(symbols) == set(UNIVERSE)
            return bars
        def get_quotes(self, symbols):
            return [Quote("alpaca", "XLF", 1, self.quote_age, 39.90, 40.0,
                          39.95, "open")]
        def list_active_assets(self, *, asset_class):
            return [{"symbol": "XLF", "tradable": True}]
        def get_balances(self): return {"cash": 100000}

    adapter = Paper()
    result = check(adapter, asof_day=asof, capital_cap=100,
                   account_breaker_clear=True, today_day=asof)
    assert result.ready and result.order_preview["quantity"] == 2
    assert result.order_preview["order_class"] == "oto"
    assert not check(adapter, asof_day=asof, capital_cap=100,
                     account_breaker_clear=False, today_day=asof).ready
    assert check(adapter, asof_day=asof, capital_cap=100,
                 account_breaker_clear=True, today_day="2026-09-23").reason == "asof_day_not_current_market_day"
    adapter.orders = [{"status": "accepted", "symbol": "ORCL"}]
    assert check(adapter, asof_day=asof, capital_cap=100,
                 account_breaker_clear=True, today_day=asof).reason == "paper_account_has_active_order"
    adapter.orders = []
    adapter.quote_age = 60
    assert check(adapter, asof_day=asof, capital_cap=100,
                 account_breaker_clear=True, today_day=asof).reason == "no_fresh_affordable_tradable_quote"
