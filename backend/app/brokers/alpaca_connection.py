"""Encrypted Alpaca credential storage and read-only connection checks."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.brokers.alpaca_adapter import AlpacaBrokerAdapter, AlpacaBrokerError
from app.brokers.robinhood_oauth import BrokerOAuthConfigurationError, _fernet
from app.models.models import BrokerConnection

BROKER = "alpaca_trading"


def connect(db: Session, api_key: str, api_secret: str, encryption_key: str, *, paper: bool) -> dict:
    """Verify the submitted key is read-only usable, then encrypt it at rest.

    This never allows order submission and never changes the app trading mode.
    """
    adapter = AlpacaBrokerAdapter(api_key, api_secret, paper=paper)
    if not adapter.authenticate():
        raise AlpacaBrokerError("Alpaca account is not active")
    blob = _fernet(encryption_key).encrypt(json.dumps({"api_key": api_key, "api_secret": api_secret,
                                                        "paper": paper}).encode()).decode()
    record = db.get(BrokerConnection, BROKER)
    if record is None:
        record = BrokerConnection(broker=BROKER, client_id="encrypted-api-key", encrypted_refresh_token=blob,
                                  status="authorized")
        db.add(record)
    else:
        record.client_id, record.encrypted_refresh_token = "encrypted-api-key", blob
        record.connected_at, record.status = datetime.utcnow(), "authorized"
    db.commit()
    return {"connected": True, "paper": paper, "execution_enabled": False}


def load_read_only_adapter(db: Session, encryption_key: str) -> tuple[AlpacaBrokerAdapter, bool]:
    """Load the encrypted credential strictly for broker reads.

    The returned adapter keeps order submission disabled. Any execution path must
    construct and gate a separate adapter during an explicit activation flow.
    """
    record = db.get(BrokerConnection, BROKER)
    if not record:
        raise BrokerOAuthConfigurationError("Alpaca has not been connected")
    try:
        payload = json.loads(_fernet(encryption_key).decrypt(record.encrypted_refresh_token.encode()).decode())
    except Exception as exc:
        raise BrokerOAuthConfigurationError("Stored Alpaca credential cannot be decrypted") from exc
    return AlpacaBrokerAdapter(payload["api_key"], payload["api_secret"], paper=bool(payload["paper"])), bool(payload["paper"])


def status(db: Session) -> dict:
    record = db.get(BrokerConnection, BROKER)
    connected = bool(record and record.status == "authorized")
    return {"broker": BROKER, "application_authorized": connected, "connected": False,
            "read_only_ready": False, "execution_enabled": False,
            "reason": ("Alpaca credentials are encrypted at rest; run read-only verification next."
                       if connected else "Alpaca has not been connected.")}


def verify_read_only(db: Session, encryption_key: str) -> dict:
    adapter, paper = load_read_only_adapter(db, encryption_key)
    from app.services.broker_readiness import verify_read_only_connection

    accounts = adapter.get_accounts()
    if len(accounts) != 1 or not accounts[0].get("account_id"):
        return {"connected": False, "read_only_ready": False, "execution_enabled": False,
                "paper": bool(payload["paper"]), "reasons": ["expected exactly one Alpaca account"]}
    report = verify_read_only_connection(adapter, str(accounts[0]["account_id"]))
    report["paper"] = paper
    return report
