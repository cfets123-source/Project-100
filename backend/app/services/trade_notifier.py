"""Turns live trade audit events into phone notifications (read-only on trading state).

Runs inside the API process: every few seconds it reads new audit_log rows written by
the trading workers and pushes a short message to every subscribed device. Paper
events are ignored. The cursor starts at "now" so history is never replayed.
"""
from __future__ import annotations

import datetime as dt
import json

from app.brokers.robinhood_oauth import _fernet
from app.models.models import AppState, AuditLogEntry, PushSubscription
from app.services import webpush

LIVE_MODES = {"live", "binance"}
EVENTS = ("allocator_buy", "allocator_sell", "allocator_buy_failed", "allocator_sell_failed",
          "allocator_broker_exit", "binance_buy", "binance_sell", "binance_buy_failed", "binance_sell_failed",
          "kill_switch_activated")
REASONS = {"stop": "stop-loss hit", "target": "target hit", "time_limit": "time limit", "rule_exit": "trend ended",
           "rotation": "swapped for a stronger pick"}


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return ""


def message_for(event_type: str, p: dict) -> dict | None:
    """Notification text for one audit event, or None when it should not notify."""
    if event_type == "kill_switch_activated":
        return {"title": "Trading halted", "body": str(p.get("reason") or "Safety stop activated"), "tag": "halt"}
    if p.get("mode") not in LIVE_MODES:
        return None
    sym = p.get("symbol", "")
    venue = "Binance.US" if p.get("mode") == "binance" else "Alpaca"
    if event_type in ("allocator_buy", "binance_buy"):
        usd = p.get("notional", p.get("usd"))
        return {"title": f"Bought {sym}", "body": f"{_money(usd)} on {venue}".strip(), "tag": f"buy-{sym}"}
    if event_type in ("allocator_sell", "binance_sell"):
        why = REASONS.get(p.get("reason"), str(p.get("reason") or "").replace("_", " "))
        return {"title": f"Sold {sym}", "body": f"{why} · {_money(p.get('price'))} on {venue}".strip(" ·"),
                "tag": f"sell-{sym}"}
    if event_type == "allocator_broker_exit":
        return {"title": f"{sym} closed at the broker", "body": "Bracket stop or target filled", "tag": f"sell-{sym}"}
    if event_type.endswith("_failed"):
        side = "Buy" if "buy" in event_type else "Sell"
        return {"title": f"{side} failed: {sym}", "body": str(p.get("error") or "")[:120], "tag": f"fail-{sym}"}
    return None


def _get(db, key):
    row = db.get(AppState, key)
    return row.value if row else None


def _put(db, key, value):
    row = db.get(AppState, key)
    if row is None:
        db.add(AppState(key=key, value=value))
    else:
        row.value = value
    db.commit()


def vapid_keys(db, encryption_key: str) -> dict:
    stored = _get(db, "vapid")
    f = _fernet(encryption_key)
    if stored:
        return json.loads(f.decrypt(stored.encode()))
    keys = webpush.generate_vapid()
    _put(db, "vapid", f.encrypt(json.dumps(keys).encode()).decode())
    return keys


def subscribe(db, sub: dict) -> None:
    endpoint, keys = str(sub.get("endpoint") or ""), sub.get("keys") or {}
    if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("invalid push subscription")
    row = db.get(PushSubscription, endpoint)
    if row is None:
        db.add(PushSubscription(endpoint=endpoint, p256dh=keys["p256dh"], auth=keys["auth"]))
    else:
        row.p256dh, row.auth = keys["p256dh"], keys["auth"]
    db.commit()


def broadcast(db, encryption_key: str, message: dict, subject: str, sender=webpush.send) -> dict:
    keys = vapid_keys(db, encryption_key)
    sent = gone = failed = 0
    for row in db.query(PushSubscription).all():
        try:
            code = sender({"endpoint": row.endpoint, "p256dh": row.p256dh, "auth": row.auth},
                          {**message, "url": "/dashboard"}, keys, subject)
        except Exception:
            failed += 1
            continue
        if code in (404, 410):
            db.delete(row)
            gone += 1
        elif 200 <= code < 300:
            sent += 1
        else:
            failed += 1
    db.commit()
    return {"sent": sent, "removed": gone, "failed": failed}


def poll(db, encryption_key: str, subject: str, sender=webpush.send) -> int:
    """Push every new live trade event since the cursor; returns notifications attempted."""
    cursor = _get(db, "notify_cursor")
    if cursor is None:
        _put(db, "notify_cursor", dt.datetime.utcnow().isoformat())
        return 0
    since = dt.datetime.fromisoformat(cursor)
    rows = (db.query(AuditLogEntry).filter(AuditLogEntry.event_type.in_(EVENTS), AuditLogEntry.timestamp > since)
            .order_by(AuditLogEntry.timestamp).limit(50).all())
    count = 0
    for row in rows:
        msg = message_for(row.event_type, row.payload if isinstance(row.payload, dict) else {})
        if msg and db.query(PushSubscription).count():
            broadcast(db, encryption_key, msg, subject, sender)
            count += 1
        since = row.timestamp
    if rows:
        _put(db, "notify_cursor", since.isoformat())
    return count
