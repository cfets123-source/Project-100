"""Rolling option watchlist: contract selection and read-only collection."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.runtime import robinhood_option_watchlist as w

TODAY = dt.date(2026, 9, 29)


def _quote_row(cid, symbol, bid, ask, oi=100, vol=10, reason="current"):
    return {"instrument_id": cid, "symbol": symbol, "bid": bid, "ask": ask, "multiplier": 100.0,
            "open_interest": oi, "volume": vol, "quality_reason": reason}


def _adapter(spot=100.0, expirations=("2026-09-30", "2026-10-02", "2026-10-09", "2026-11-20"),
             price_for=lambda strike, typ: 0.4):
    adapter = MagicMock()
    adapter.get_quotes.return_value = [SimpleNamespace(bid=spot - 0.01, ask=spot + 0.01)]
    adapter.get_option_chains.return_value = [
        {"id": str(uuid4()), "symbol": "XYZ", "expiration_dates": list(expirations), "can_open_position": True}]
    made = {}

    def instruments(chain_id, expiration, strike, typ):
        cid = str(uuid4())
        made[cid] = (float(strike), typ, expiration)
        return [{"id": cid, "state": "active", "tradability": "tradable"}]

    def quotes(batch):
        assert 1 <= len(batch) <= 20
        return [_quote_row(c["id"], "XYZ", 0.01 if price_for(*made[c["id"]][:2]) > 0 else 0,
                           price_for(*made[c["id"]][:2])) for c in batch]

    adapter.get_option_instruments.side_effect = instruments
    adapter.get_option_quotes.side_effect = quotes
    adapter.made = made
    return adapter


def test_expirations_limited_to_dte_window_and_count():
    cfg = w.WatchlistConfig()
    assert w.pick_expirations(["2026-09-29", "2026-09-30", "2026-10-02", "2026-10-09", "2026-11-20"],
                              TODAY, cfg) == ["2026-09-30", "2026-10-02"]


def test_candidate_strikes_move_out_of_the_money():
    assert w.candidate_strikes(101.2, "call", 3) == [101.0, 102.0, 103.0, 104.0]
    assert w.candidate_strikes(101.2, "put", 3) == [101.0, 100.0, 99.0, 98.0]
    assert w.strike_increment(20) == 0.5 and w.strike_increment(600) == 5.0


def test_selects_only_affordable_contracts_and_caps_per_underlying():
    # contracts further out of the money are cheaper; only asks <= $1.00 fit a $100 budget
    adapter = _adapter(price_for=lambda strike, typ: max(0.0, 3.0 - 0.5 * abs(strike - 100)))
    cfg = w.WatchlistConfig(underlyings=("XYZ",), per_underlying=5)
    picked = w.select_underlying(adapter, "XYZ", TODAY, cfg)
    assert 0 < len(picked) <= 5
    assert all(p["ask"] * 100 <= cfg.max_premium_usd and p["ask"] >= cfg.min_ask for p in picked)
    # only the two nearest expirations were queried
    assert {e for (_, _, e) in adapter.made.values()} == {"2026-09-30", "2026-10-02"}


def test_one_failing_underlying_does_not_stop_the_others():
    good = _adapter()
    bad = MagicMock()
    bad.get_quotes.side_effect = RuntimeError("boom")

    class Router:
        def __getattr__(self, name):
            return getattr(good, name)

        def get_quotes(self, symbols):
            return bad.get_quotes(symbols) if symbols == ["BAD"] else good.get_quotes(symbols)

    result = w.build_watchlist(Router(), TODAY, w.WatchlistConfig(underlyings=("BAD", "XYZ")))
    assert result["failures"] == {"BAD": "RuntimeError"}
    assert result["per_symbol"]["XYZ"] > 0 and result["order_submission"] is False


def test_market_hours_gate():
    assert w.market_open(dt.datetime(2026, 9, 29, 14, 0, tzinfo=dt.timezone.utc))      # Tue 10:00 ET
    assert not w.market_open(dt.datetime(2026, 9, 27, 14, 0, tzinfo=dt.timezone.utc))  # Sunday
    assert not w.market_open(dt.datetime(2026, 9, 29, 21, 0, tzinfo=dt.timezone.utc))  # 17:00 ET


def test_collection_batches_by_twenty_and_isolates_failures(monkeypatch):
    calls = []

    def fake_collect(db, adapter, batch):
        calls.append(len(batch))
        if len(calls) == 2:
            raise ValueError("expired contract")
        return {"new_quotes": len(batch)}

    monkeypatch.setattr(w, "collect_once", fake_collect)
    db = MagicMock()
    out = w.collect_watchlist(db, MagicMock(), [str(uuid4()) for _ in range(45)])
    assert calls == [20, 20, 5]
    assert out["new_quotes"] == 25 and out["failed_contracts"] == 20 and out["order_submission"] is False
    db.rollback.assert_called_once()


def test_module_has_no_order_methods():
    source = open(w.__file__).read()
    for forbidden in ("place_order", "preview_order", "cancel_order", "submit_order"):
        assert forbidden not in source
