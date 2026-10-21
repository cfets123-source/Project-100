"""Prop-challenge feed: pairing, authenticated ingest, dedupe, missed-start alert, app page."""
import datetime as dt

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import models
from app.services import prop_feed

ET = prop_feed.ET


def _reset():
    db = SessionLocal()
    for k in ("prop_token_hash", "prop_latest", "prop_events", "prop_missed_alert"):
        row = db.get(models.AppState, k)
        if row:
            db.delete(row)
    db.commit()
    db.close()


def test_feed_requires_pairing_and_dedupes_events():
    _reset()
    with TestClient(app) as client:
        assert client.post("/prop/feed", json={}).status_code == 401
        token = client.post("/prop/pair").json()["token"]
        assert client.post("/prop/feed", json={}, headers={"X-Prop-Token": "wrong"}).status_code == 401
        ev = {"id": "e1", "time": "2026-10-22T14:05:00Z", "kind": "buy", "text": "Bought 2 MNQ", "price": 21000.5}
        body = {"status": {"balance": 50000, "open_pnl": 12.5, "position": 2}, "orders": False, "account": "50KTC",
                "contract": "CON.F.US.MNQ.Z26", "bars": [["2026-10-22T14:00:00Z", 1, 2, 0.5, 1.5]], "events": [ev]}
        r = client.post("/prop/feed", json=body, headers={"X-Prop-Token": token})
        assert r.status_code == 200
        client.post("/prop/feed", json=body, headers={"X-Prop-Token": token})  # same event again
        st = client.get("/prop/state").json()
        assert st["paired"] and st["online"] and len(st["events"]) == 1
        assert st["latest"]["status"]["position"] == 2 and st["latest"]["bars"][0][4] == 1.5
        new = client.post("/prop/pair").json()["token"]  # re-pairing invalidates the old token
        assert client.post("/prop/feed", json={}, headers={"X-Prop-Token": token}).status_code == 401
        assert client.post("/prop/feed", json={}, headers={"X-Prop-Token": new}).status_code == 200
        page = client.get("/prop")
        assert page.status_code == 200 and "Prop Challenge" in page.text


def test_missed_start_alert_once_per_weekday():
    _reset()
    db = SessionLocal()
    prop_feed.pair(db)
    mon = dt.datetime(2026, 10, 26, 10, 0, tzinfo=ET)
    assert prop_feed.missed_start(db, mon)["tag"] == "prop-missed"
    assert prop_feed.missed_start(db, mon + dt.timedelta(minutes=5)) is None      # once per day
    sat = dt.datetime(2026, 10, 24, 10, 0, tzinfo=ET)
    assert prop_feed.missed_start(db, sat) is None
    tue = dt.datetime(2026, 10, 27, 10, 0, tzinfo=ET)
    prop_feed.ingest(db, {"status": {}}, now=dt.datetime(2026, 10, 27, 9, 25, tzinfo=ET))
    assert prop_feed.missed_start(db, tue) is None                                 # reported after 9:20
    db.close()


def test_server_never_places_prop_orders():
    import inspect
    src = inspect.getsource(prop_feed)
    assert "Order/place" not in src and "topstepx" not in src.lower().replace("topstep forbids", "")
