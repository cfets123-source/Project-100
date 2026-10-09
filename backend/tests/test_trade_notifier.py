"""Phone app shell + Web Push trade alerts."""
import datetime as dt

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import models
from app.services import trade_notifier as n

KEY = Fernet.generate_key().decode()


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_messages_live_only_and_readable():
    assert n.message_for("allocator_buy", {"mode": "paper", "symbol": "EWT"}) is None
    m = n.message_for("allocator_sell", {"mode": "live", "symbol": "QLD", "reason": "stop", "price": 93.1})
    assert m["title"] == "Sold QLD" and "stop-loss hit" in m["body"] and "$93.10" in m["body"]
    assert n.message_for("binance_buy", {"mode": "binance", "symbol": "SOL/USD", "usd": 33})["body"] == "$33.00 on Binance.US"
    assert n.message_for("binance_buy", {"mode": "binance-paper", "symbol": "SOL/USD"}) is None
    assert n.message_for("kill_switch_activated", {"reason": "x"})["title"] == "Trading halted"


def test_poll_starts_at_now_then_pushes_new_live_events_and_drops_dead_devices():
    db, sent = _db(), []
    db.add(models.AuditLogEntry(event_type="allocator_buy", payload={"mode": "live", "symbol": "OLD"},
                                timestamp=dt.datetime.utcnow() - dt.timedelta(minutes=5)))
    db.commit()
    n.subscribe(db, {"endpoint": "https://push.example/a", "keys": {"p256dh": "p", "auth": "a"}})
    n.subscribe(db, {"endpoint": "https://push.example/gone", "keys": {"p256dh": "p", "auth": "a"}})

    def sender(sub, msg, keys, subject):
        sent.append((sub["endpoint"], msg["title"]))
        assert keys["public_key"] and "private_pem" in keys
        return 410 if sub["endpoint"].endswith("gone") else 201

    assert n.poll(db, KEY, "https://x", sender) == 0  # history is never replayed
    for p in ({"mode": "paper", "symbol": "EWT"}, {"mode": "live", "symbol": "XLE", "notional": 10.5}):
        db.add(models.AuditLogEntry(event_type="allocator_buy", payload=p,
                                    timestamp=dt.datetime.utcnow() + dt.timedelta(seconds=1)))
    db.commit()
    assert n.poll(db, KEY, "https://x", sender) == 1
    assert sent == [("https://push.example/a", "Bought XLE"), ("https://push.example/gone", "Bought XLE")]
    assert [r.endpoint for r in db.query(models.PushSubscription).all()] == ["https://push.example/a"]
    assert n.poll(db, KEY, "https://x", sender) == 0  # cursor advanced
    assert n.vapid_keys(db, KEY) == n.vapid_keys(db, KEY)  # stable keys


def test_subscribe_rejects_non_https():
    db = _db()
    try:
        n.subscribe(db, {"endpoint": "http://evil", "keys": {"p256dh": "p", "auth": "a"}})
        raise AssertionError("should reject")
    except ValueError:
        pass


def test_manifest_and_service_worker_are_public():
    from app.main import app
    with TestClient(app) as client:
        m = client.get("/manifest.webmanifest")
        sw = client.get("/sw.js")
        page = client.get("/dashboard").text
    assert m.status_code == 200 and m.json()["display"] == "standalone" and m.json()["start_url"] == "/dashboard"
    assert sw.status_code == 200 and "showNotification" in sw.text and sw.headers["service-worker-allowed"] == "/"
    assert 'rel="manifest"' in page and 'id="alerts"' in page
