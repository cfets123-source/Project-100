"""Encrypted Alpaca credential storage and read-only connection checks."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.brokers.alpaca_adapter import AlpacaBrokerAdapter, AlpacaBrokerError
from app.brokers.robinhood_oauth import BrokerOAuthConfigurationError, _fernet
from app.models.models import BrokerConnection

# Keep paper and live credentials in distinct encrypted records.  A live
# read-only verification must never replace the paper credential that powers
# the monitor and paper-lifecycle checks.
PAPER_BROKER = "alpaca_trading"
LIVE_BROKER = "alpaca_trading_live"
# Backward-compatible name for paper-only runtime callers.
BROKER = PAPER_BROKER


def broker_record_name(*, paper: bool) -> str:
    return PAPER_BROKER if paper else LIVE_BROKER


def _record(db: Session, *, paper: bool):
    return db.get(BrokerConnection, broker_record_name(paper=paper))


def connect(db: Session, api_key: str, api_secret: str, encryption_key: str, *, paper: bool) -> dict:
    """Verify the submitted key is read-only usable, then encrypt it at rest.

    This never allows order submission and never changes the app trading mode.
    """
    adapter = AlpacaBrokerAdapter(api_key, api_secret, paper=paper)
    if not adapter.authenticate():
        raise AlpacaBrokerError("Alpaca account is not active")
    blob = _fernet(encryption_key).encrypt(json.dumps({"api_key": api_key, "api_secret": api_secret,
                                                        "paper": paper}).encode()).decode()
    record = _record(db, paper=paper)
    if record is None:
        record = BrokerConnection(broker=broker_record_name(paper=paper), client_id="encrypted-api-key", encrypted_refresh_token=blob,
                                  status="authorized")
        db.add(record)
    else:
        record.client_id, record.encrypted_refresh_token = "encrypted-api-key", blob
        record.connected_at, record.status = datetime.utcnow(), "authorized"
    db.commit()
    return {"connected": True, "paper": paper, "execution_enabled": False}


def load_read_only_adapter(db: Session, encryption_key: str, *, paper: bool = True) -> tuple[AlpacaBrokerAdapter, bool]:
    """Load the encrypted credential strictly for broker reads.

    The returned adapter keeps order submission disabled. Any execution path must
    construct and gate a separate adapter during an explicit activation flow.
    """
    record = _record(db, paper=paper)
    if not record:
        raise BrokerOAuthConfigurationError("Alpaca has not been connected")
    try:
        payload = json.loads(_fernet(encryption_key).decrypt(record.encrypted_refresh_token.encode()).decode())
    except Exception as exc:
        raise BrokerOAuthConfigurationError("Stored Alpaca credential cannot be decrypted") from exc
    return AlpacaBrokerAdapter(payload["api_key"], payload["api_secret"], paper=bool(payload["paper"])), bool(payload["paper"])


def status(db: Session, *, paper: bool = True) -> dict:
    record = _record(db, paper=paper)
    connected = bool(record and record.status == "authorized")
    return {"broker": "alpaca_trading", "paper": paper, "application_authorized": connected, "connected": False,
            "read_only_ready": False, "execution_enabled": False,
            "reason": ("Alpaca credentials are encrypted at rest; run read-only verification next."
                       if connected else "Alpaca has not been connected.")}


def verify_read_only(db: Session, encryption_key: str, *, paper: bool = True) -> dict:
    adapter, paper = load_read_only_adapter(db, encryption_key, paper=paper)
    from app.services.broker_readiness import verify_read_only_connection

    accounts = adapter.get_accounts()
    if len(accounts) != 1 or not accounts[0].get("account_id"):
        return {"connected": False, "read_only_ready": False, "execution_enabled": False,
                "paper": paper, "reasons": ["expected exactly one Alpaca account"]}
    report = verify_read_only_connection(adapter, str(accounts[0]["account_id"]))
    report["paper"] = paper
    return report


def load_paper_execution_adapter(db: Session, encryption_key: str, *, enabled: bool) -> AlpacaBrokerAdapter:
    """Return a submitting adapter only for an explicitly enabled paper account."""
    adapter, paper = load_read_only_adapter(db, encryption_key)
    if not enabled:
        raise BrokerOAuthConfigurationError("Alpaca paper execution gate is disabled")
    if not paper:
        raise BrokerOAuthConfigurationError("refusing to construct execution adapter for live credential")
    return AlpacaBrokerAdapter(adapter.headers["APCA-API-KEY-ID"], adapter.headers["APCA-API-SECRET-KEY"],
                               paper=True, allow_order_submission=True)


def load_live_execution_adapter(db: Session, encryption_key: str, *, enabled: bool) -> AlpacaBrokerAdapter:
    """Construct a submitting live adapter only at the final activation gate."""
    adapter, paper = load_read_only_adapter(db, encryption_key, paper=False)
    if not enabled:
        raise BrokerOAuthConfigurationError("live execution gate is disabled")
    if paper:
        raise BrokerOAuthConfigurationError("refusing live execution with a paper credential")
    return AlpacaBrokerAdapter(adapter.headers["APCA-API-KEY-ID"], adapter.headers["APCA-API-SECRET-KEY"],
                               paper=False, allow_order_submission=True)
