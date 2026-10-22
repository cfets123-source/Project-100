"""Prop-challenge feed: the bot on the owner's Mac reports its status here; the app only displays it.

The server never places prop-account orders (Topstep forbids orders from remote servers). The Mac authenticates
with a pairing token whose SHA-256 hash is stored; the token itself is shown once, at pairing.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets
from zoneinfo import ZoneInfo

from app.models.models import AppState

ET = ZoneInfo("America/New_York")
MAX_EVENTS = 300
MAX_BARS = 90
MAX_ACCOUNTS = 20
PUSH_KINDS = {"buy", "sell", "flat", "halt", "pass", "error"}


def _get(db, key, default=None):
    row = db.get(AppState, key)
    return json.loads(row.value) if row else default


def _put(db, key, value):
    row = db.get(AppState, key)
    text = json.dumps(value, default=str)
    if row is None:
        db.add(AppState(key=key, value=text))
    else:
        row.value = text


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def pair(db) -> str:
    token = secrets.token_urlsafe(24)
    _put(db, "prop_token_hash", _hash(token))
    db.commit()
    return token


def verify(db, token: str | None) -> bool:
    stored = _get(db, "prop_token_hash")
    return bool(token and stored and hmac.compare_digest(stored, _hash(token)))


def _clean_bars(bars):
    out = []
    for b in (bars or [])[-MAX_BARS:]:
        try:
            out.append([str(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4])])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _clean_accounts(accounts):
    out = []
    for a in (accounts or [])[:MAX_ACCOUNTS]:
        if isinstance(a, dict):
            out.append({"account": str(a.get("account") or "")[:80], "orders": bool(a.get("orders")),
                        "contract": str(a.get("contract") or "")[:40],
                        "status": a.get("status") if isinstance(a.get("status"), dict) else {}})
    return out


def ingest(db, payload: dict, now: dt.datetime | None = None) -> list[dict]:
    """Store the latest status and new events. Returns events that should be pushed to phones."""
    now = now or dt.datetime.now(dt.timezone.utc)
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    latest = {"received_at": now.isoformat(), "status": status, "bars": _clean_bars(payload.get("bars")),
              "account": str(payload.get("account") or "")[:80], "orders": bool(payload.get("orders")),
              "contract": str(payload.get("contract") or "")[:40], "accounts": _clean_accounts(payload.get("accounts"))}
    _put(db, "prop_latest", latest)
    events = _get(db, "prop_events", [])
    seen = {e.get("id") for e in events}
    fresh = []
    for e in payload.get("events") or []:
        if not isinstance(e, dict) or not e.get("id") or e["id"] in seen:
            continue
        clean = {k: e.get(k) for k in ("id", "time", "kind", "text", "price", "size", "pnl", "account")}
        clean["text"] = str(clean.get("text") or "")[:200]
        clean["account"] = str(clean.get("account") or "")[:80] or None
        fresh.append(clean)
        seen.add(e["id"])
    if fresh:
        _put(db, "prop_events", (events + fresh)[-MAX_EVENTS:])
    db.commit()
    return [e for e in fresh if e.get("kind") in PUSH_KINDS]


def state(db, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    latest = _get(db, "prop_latest")
    age = None
    if latest:
        age = (now - dt.datetime.fromisoformat(latest["received_at"])).total_seconds()
    return {"paired": _get(db, "prop_token_hash") is not None, "latest": latest,
            "events": list(reversed(_get(db, "prop_events", [])))[:100],
            "heartbeat_age_s": round(age) if age is not None else None,
            "online": age is not None and age < 120}


def missed_start(db, now: dt.datetime | None = None) -> dict | None:
    """Weekdays 9:40 AM-3:00 PM ET: if the bot has not reported since 9:20 AM, return one alert per day."""
    now = now or dt.datetime.now(dt.timezone.utc)
    local = now.astimezone(ET)
    if local.weekday() >= 5 or not (dt.time(9, 40) <= local.time() <= dt.time(15, 0)):
        return None
    if _get(db, "prop_token_hash") is None or _get(db, "prop_missed_alert") == local.date().isoformat():
        return None
    latest = _get(db, "prop_latest")
    start = dt.datetime.combine(local.date(), dt.time(9, 20), ET)
    if latest and dt.datetime.fromisoformat(latest["received_at"]) >= start:
        return None
    _put(db, "prop_missed_alert", local.date().isoformat())
    db.commit()
    return {"title": "Prop bot is not running",
            "body": "No report from your Mac since 9:20 AM. Is it on, awake and online? Today's trades are being missed.",
            "tag": "prop-missed", "url": "/prop"}


def push_message(event: dict) -> dict:
    titles = {"buy": "Prop: bought", "sell": "Prop: sold", "flat": "Prop: flat", "halt": "Prop: stopped",
              "pass": "Prop: CHALLENGE PASSED", "error": "Prop: problem"}
    acct = (event.get("account") or "").split("-")[0]  # e.g. "50KTC" so several accounts are distinguishable
    body = ("%s: " % acct if acct else "") + (event.get("text") or "")
    return {"title": titles.get(event.get("kind"), "Prop bot"), "body": body,
            "tag": "prop-" + str(event.get("id")), "url": "/prop"}
