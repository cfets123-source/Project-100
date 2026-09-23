"""Encrypted, user-authorized E*TRADE session; no order execution."""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.brokers.etrade_adapter import ETradeError, ETradeReadOnlyAdapter
from app.brokers.robinhood_oauth import _fernet
from app.models.models import BrokerConnection, BrokerOAuthState

BROKER = "etrade_personal"


def _configured_adapter() -> ETradeReadOnlyAdapter:
    return ETradeReadOnlyAdapter(os.getenv("ETRADE_CONSUMER_KEY", ""),
                                os.getenv("ETRADE_CONSUMER_SECRET", ""))


def status(db: Session) -> dict:
    record = db.get(BrokerConnection, BROKER)
    today_et = dt.datetime.now(ZoneInfo("America/New_York")).date()
    authorized_today = bool(record and record.status == "authorized" and
                            record.connected_at.replace(tzinfo=dt.timezone.utc)
                            .astimezone(ZoneInfo("America/New_York")).date() == today_et)
    return {"broker": BROKER,
            "api_key_configured": bool(os.getenv("ETRADE_CONSUMER_KEY") and
                                       os.getenv("ETRADE_CONSUMER_SECRET")),
            "application_authorized_today": authorized_today,
            "execution_enabled": False,
            "reason": ("Read-only E*TRADE authorization recorded today; order execution is not built."
                       if authorized_today else "E*TRADE OAuth must be completed each trading day."
                       if record else "E*TRADE live API key and user authorization are required.")}


def begin(db: Session, encryption_key: str) -> tuple[str, str]:
    adapter = _configured_adapter()
    request_token, request_secret = adapter.request_token()
    state = BrokerOAuthState(state="etrade:" + request_token,
        code_verifier=_fernet(encryption_key).encrypt(request_secret.encode()).decode(),
        client_id=adapter.consumer_key,
        expires_at=dt.datetime.utcnow() + dt.timedelta(minutes=5))
    db.merge(state)
    db.commit()
    return adapter.authorization_url(request_token), request_token


def finish(db: Session, encryption_key: str, request_token: str, verifier: str) -> dict:
    pending = db.get(BrokerOAuthState, "etrade:" + request_token)
    if pending is None or pending.expires_at < dt.datetime.utcnow():
        raise ETradeError("E*TRADE authorization expired; reconnect and try again")
    adapter = _configured_adapter()
    if adapter.consumer_key != pending.client_id:
        raise ETradeError("E*TRADE API key changed during authorization")
    try:
        request_secret = _fernet(encryption_key).decrypt(pending.code_verifier.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ETradeError("E*TRADE temporary credential cannot be decrypted") from exc
    access_token, access_secret = adapter.exchange_verifier(request_token, request_secret, verifier)
    reader = ETradeReadOnlyAdapter(adapter.consumer_key, adapter.consumer_secret,
                                  access_token=access_token, access_secret=access_secret)
    accounts = reader.list_accounts()
    if not any(a["status"] == "ACTIVE" and a["institution_type"] == "BROKERAGE" for a in accounts):
        raise ETradeError("E*TRADE returned no active personal brokerage account")
    encrypted = _fernet(encryption_key).encrypt(json.dumps({
        "access_token": access_token, "access_secret": access_secret}).encode()).decode()
    record = db.get(BrokerConnection, BROKER)
    if record is None:
        record = BrokerConnection(broker=BROKER, client_id=adapter.consumer_key,
                                  encrypted_refresh_token=encrypted, status="authorized")
        db.add(record)
    else:
        record.client_id = adapter.consumer_key
        record.encrypted_refresh_token = encrypted
        record.status = "authorized"
        record.connected_at = dt.datetime.utcnow()
    db.delete(pending)
    db.commit()
    return {"connected": True, "accounts": [{"last4": a["account_last4"],
            "type": a["account_type"]} for a in accounts], "execution_enabled": False}


def reader(db: Session, encryption_key: str) -> ETradeReadOnlyAdapter:
    if not status(db)["application_authorized_today"]:
        raise ETradeError("E*TRADE session is not authorized today")
    record = db.get(BrokerConnection, BROKER)
    adapter = _configured_adapter()
    if adapter.consumer_key != record.client_id:
        raise ETradeError("E*TRADE API key changed; reconnect")
    try:
        tokens = json.loads(_fernet(encryption_key).decrypt(
            record.encrypted_refresh_token.encode()).decode())
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise ETradeError("E*TRADE session cannot be decrypted") from exc
    return ETradeReadOnlyAdapter(adapter.consumer_key, adapter.consumer_secret,
        access_token=tokens["access_token"], access_secret=tokens["access_secret"])
