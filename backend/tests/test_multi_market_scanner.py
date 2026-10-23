"""Watch-only multi-market scanner: frozen rules, outcome tracking, no order path."""
import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import models
from app.research import multi_market_rules as mm
from app.runtime import multi_market_scanner as scanner


def bars_from(closes, start=dt.date(2025, 1, 1), spread=.005):
    out, d = [], start
    for c in closes:
        out.append({"timestamp": d.isoformat(), "open": c, "high": c * (1 + spread),
                    "low": c * (1 - spread), "close": c, "volume": 1e6})
        d += dt.timedelta(days=1)
    return out


def rising(n=260, start=100.0, step=.2):
    return [start + i * step for i in range(n)]


def test_breakout_fires_on_new_high_above_200d():
    closes = rising() + [rising()[-1] * 1.03]
    sig = mm.signals_on_last_bar("SPY", bars_from(closes))
    assert any(s["rule"] == "breakout" for s in sig)
    assert all(s["group"] == "index/sector ETF" for s in sig)


def test_pullback_fires_on_sharp_dip_in_uptrend():
    closes = rising() + [rising()[-1] * .97, rising()[-1] * .94]
    rules = {s["rule"] for s in mm.signals_on_last_bar("TQQQ", bars_from(closes))}
    assert "pullback" in rules and "breakout" not in rules


def test_no_signals_in_downtrend_or_short_history():
    falling = [200 - i * .3 for i in range(260)]
    assert mm.signals_on_last_bar("SPY", bars_from(falling)) == []
    assert mm.signals_on_last_bar("SPY", bars_from(rising(100))) == []


def test_evaluate_target_stop_and_waiting():
    base = bars_from(rising() + [rising()[-1] * 1.03])
    day = base[-1]["timestamp"]
    assert mm.evaluate("breakout", base, day)["status"] == "waiting_entry"
    up = base + bars_from([base[-1]["close"] * k for k in (1.0, 1.08, 1.2)],
                          start=dt.date.fromisoformat(day) + dt.timedelta(days=1))
    out = mm.evaluate("breakout", up, day)
    assert out["status"] == "closed" and out["exit_reason"] == "target" and out["result_pct"] > .14
    down = base + bars_from([base[-1]["close"] * k for k in (1.0, .9)],
                            start=dt.date.fromisoformat(day) + dt.timedelta(days=1))
    out = mm.evaluate("breakout", down, day)
    assert out["exit_reason"] == "stop" and out["result_pct"] < -.069


def test_record_is_idempotent_and_tracks_outcome():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    base = bars_from(rising() + [rising()[-1] * 1.03])
    with Session(engine) as db:
        first = scanner.record(db, {"SPY": base})
        again = scanner.record(db, {"SPY": base})
        assert first["new_signals"] >= 1 and again["new_signals"] == 0
        later = base + bars_from([base[-1]["close"] * k for k in (1.0, 1.2)],
                                 start=dt.date.fromisoformat(base[-1]["timestamp"]) + dt.timedelta(days=1))
        scanner.record(db, {"SPY": later})
        row = db.query(models.ScannerSignal).filter_by(rule="breakout", signal_date=base[-1]["timestamp"]).one()
        assert row.status == "closed" and row.result_pct > 0 and first["order_submission"] is False


def test_due_only_after_close_once_per_weekday():
    fri = dt.datetime(2026, 10, 2, 21, 0, tzinfo=dt.timezone.utc)   # 17:00 ET Friday
    assert scanner.due(fri, None) and not scanner.due(fri, "2026-10-02")
    assert not scanner.due(dt.datetime(2026, 10, 2, 19, 0, tzinfo=dt.timezone.utc), None)  # 15:00 ET
    assert not scanner.due(dt.datetime(2026, 10, 3, 21, 0, tzinfo=dt.timezone.utc), None)  # Saturday


def test_scanner_has_no_order_methods():
    for module in (mm, scanner):
        src = open(module.__file__).read()
        for word in ("place_order", "submit_order", "cancel_order", "preview_order"):
            assert word not in src


def test_scanner_endpoint_shape(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        d = client.get("/scanner/signals").json()
        assert d["order_submission"] is False and set(d["rules"]) == {"trend", "pullback", "breakout"}
        assert "Market scanner" in client.get("/dashboard").text


def test_backfill_records_recent_history_once():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    closes = rising() + [rising()[-1] * 1.03] + [rising()[-1] * 1.03 * (1 + .012 * k) for k in range(1, 6)]
    with Session(engine) as db:
        out = scanner.record(db, {"QQQ": bars_from(closes)}, backfill_days=5)
        dates = {r.signal_date for r in db.query(models.ScannerSignal).all()}
        assert out["new_signals"] >= 2 and len(dates) >= 2
        assert scanner.record(db, {"QQQ": bars_from(closes)}, backfill_days=5)["new_signals"] == 0
