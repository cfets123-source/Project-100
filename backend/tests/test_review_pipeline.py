"""Stress gate on approval, nightly review flags, strategy pipeline stages."""
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import models
from app.research import stress_gate
from app.services import nightly_review as nr
from app.services import owner_experiment as oe
from app.services.pipeline import pipeline

NIGHT = dt.datetime(2026, 10, 8, 0, 30, tzinfo=dt.timezone.utc)  # 20:30 ET Wed 7 Oct


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_committed_stress_results_pass_and_gate_blocks_unknown(monkeypatch):
    assert stress_gate.stress_passed("allocator-core-satellite-v1") == (True, "")
    assert stress_gate.stress_passed("binance-crypto-signals-v1") == (True, "")
    monkeypatch.setattr(stress_gate, "stress_result", lambda s: {"passed": False})
    with pytest.raises(ValueError, match="stress_gate:stress_test_failed"):
        oe.accept(_db(), "binance-crypto-signals-v1", accepted_by="owner", max_equity=1000, floor_equity=50,
                  acknowledgement=oe.ACKNOWLEDGEMENT)


def test_nightly_review_flags_failures_bad_day_and_idle_worker():
    db = _db()
    db.add(models.AllocatorLot(id="a", mode="live", sleeve="satellite", symbol="EWT", rule="breakout", quantity=0.1,
                               entry_price=116, stop_price=107.9, target_price=133.4, max_hold_days=30,
                               opened_on="2026-10-07", status="open"))
    db.add(models.AllocatorState(mode="live", peak_equity=110.0, last_daily_review="2026-10-06", halted=False))
    db.add(models.AuditLogEntry(event_type="allocator_sell_failed", timestamp=dt.datetime(2026, 10, 7, 18),
                                payload={"mode": "live", "symbol": "QLD", "error": "x"}))
    db.add(models.AuditLogEntry(event_type="allocator_buy", timestamp=dt.datetime(2026, 10, 7, 15),
                                payload={"mode": "paper", "symbol": "ROKU"}))
    db.commit()
    nr._put(db, "nightly_equity", {"live": 105.0})
    report = nr.build(db, {"live": 97.0}, NIGHT)
    acct = report["accounts"][0]
    texts = " | ".join(f["text"] for f in acct["flags"])
    assert "failed order" in texts and "worse than 99% of backtest days" in texts and "daily check" in texts
    assert acct["trades"] == [] and report["issues"] == 3
    assert report["lines"][0].startswith("Alpaca allocator (live): $97.00 (-7.6%)")
    assert nr.latest(db)["day"] == "2026-10-07" and not nr.due(db, NIGHT)
    assert nr.due(db, NIGHT + dt.timedelta(days=1))


def test_run_if_due_pushes_once_per_night(monkeypatch):
    db, pushed = _db(), []
    monkeypatch.setattr(nr, "collect_equities", lambda db, key: {"live": None})
    db.add(models.AllocatorLot(id="a", mode="live", sleeve="core", symbol="TQQQ", rule="stage-runner", quantity=1,
                               entry_price=77.7, stop_price=58.3, target_price=116.6, max_hold_days=10000,
                               opened_on="2026-10-07", status="open"))
    db.commit()
    assert nr.run_if_due(db, "k", pushed.append, NIGHT - dt.timedelta(hours=1)) is None  # before 20:05 ET
    assert nr.run_if_due(db, "k", pushed.append, NIGHT)["day"] == "2026-10-07"
    assert nr.run_if_due(db, "k", pushed.append, NIGHT + dt.timedelta(minutes=5)) is None
    assert len(pushed) == 1 and pushed[0]["tag"] == "nightly"


def test_pipeline_stages_from_evidence():
    db = _db()
    db.add(models.ScannerSignal(id="s", rules_version="v1", symbol="XLE", rule="breakout", asset_group="x",
                                signal_date="2026-10-07", signal_close=1, stop_pct=.07, target_pct=.15, max_hold=30,
                                status="waiting_entry"))
    for mode in ("paper", "live"):
        db.add(models.AllocatorLot(id=mode, mode=mode, sleeve="satellite", symbol="EWT", rule="breakout",
                                   quantity=0.1, entry_price=1, stop_price=1, target_price=1, max_hold_days=30,
                                   opened_on="2026-10-07", status="open"))
    db.add(models.OwnerAcceptedExperiment(strategy="allocator-core-satellite-v1", accepted_by="o", max_equity=1,
                                          floor_equity=0.5, acknowledgement="x"))
    db.commit()
    p = {s["id"]: s for s in pipeline(db)["strategies"]}
    assert p["allocator-core-satellite-v1"]["stage"] == "Nightly review"
    assert p["binance-crypto-signals-v1"]["stage"] == "Paper"
    assert [x["status"] for x in p["binance-crypto-signals-v1"]["stages"]][:4] == ["done", "done", "done", "current"]
    assert p["options-watchlist"]["stage"] == "Backtest"
