"""Robinhood Trading MCP OAuth setup; deliberately read-only after connection.

The authenticated Codex desktop session is not reused here. This service creates
its own PKCE OAuth session and stores only an encrypted refresh token. A later
adapter must still pass read-only verification before it can report connected.
"""
import base64
import datetime as dt
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.models import AuditLogEntry, BrokerConnection, BrokerOAuthState

MCP_URL = "https://agent.robinhood.com/mcp/trading"
REGISTRATION_URL = "https://agent.robinhood.com/oauth/trading/register"
AUTHORIZATION_URL = "https://robinhood.com/oauth"
TOKEN_URL = "https://api.robinhood.com/oauth2/token/"
SCOPE = "internal"
BROKER = "robinhood_agentic_trading"


class BrokerOAuthConfigurationError(ValueError):
    pass


def _code_challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def _fernet(key):
    if not key:
        raise BrokerOAuthConfigurationError("BROKER_TOKEN_ENCRYPTION_KEY is required for broker OAuth")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise BrokerOAuthConfigurationError("BROKER_TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from exc


def start_connection(db: Session, redirect_url: str):
    """Dynamically register a public OAuth client and prepare a PKCE redirect.

    Calling this function is the point where an operator will be sent to
    Robinhood. It never fetches account data or invokes an MCP tool.
    """
    if not redirect_url.startswith("https://"):
        raise BrokerOAuthConfigurationError("BROKER_OAUTH_REDIRECT_URL must be an HTTPS URL")
    registration = {
        "client_name": "Project 100",
        "redirect_uris": [redirect_url],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    }
    response = httpx.post(REGISTRATION_URL, json=registration, timeout=15)
    response.raise_for_status()
    client_id = response.json().get("client_id")
    if not isinstance(client_id, str) or not client_id:
        raise BrokerOAuthConfigurationError("Robinhood registration did not return a client ID")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    db.add(BrokerOAuthState(state=state, code_verifier=verifier, client_id=client_id,
                            expires_at=dt.datetime.utcnow() + dt.timedelta(minutes=10)))
    db.commit()
    return AUTHORIZATION_URL + "?" + urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_url,
        "scope": SCOPE, "state": state, "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "S256", "resource": MCP_URL,
    })


def finish_connection(db: Session, state: str, code: str, redirect_url: str, encryption_key: str):
    pending = db.get(BrokerOAuthState, state)
    if pending is None or pending.expires_at < dt.datetime.utcnow():
        raise BrokerOAuthConfigurationError("OAuth state is invalid or expired")
    try:
        response = httpx.post(TOKEN_URL, data={
            "grant_type": "authorization_code", "client_id": pending.client_id,
            "code": code, "redirect_uri": redirect_url, "code_verifier": pending.code_verifier,
        }, timeout=15)
        response.raise_for_status()
        refresh_token = response.json().get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise BrokerOAuthConfigurationError("Robinhood token response did not include a refresh token")
        token = _fernet(encryption_key).encrypt(refresh_token.encode()).decode()
        connection = db.get(BrokerConnection, BROKER)
        if connection is None:
            connection = BrokerConnection(broker=BROKER, client_id=pending.client_id,
                                          encrypted_refresh_token=token, status="authorized")
            db.add(connection)
        else:
            connection.client_id, connection.encrypted_refresh_token = pending.client_id, token
            connection.connected_at, connection.status = dt.datetime.utcnow(), "authorized"
        db.delete(pending)
        # A new authorization replaces the old token family; drop any access token
        # cached from it so every worker refreshes with the new refresh token.
        db.execute(text("CREATE TABLE IF NOT EXISTS robinhood_access_cache "
                        "(id TEXT PRIMARY KEY, token TEXT NOT NULL, expires_at REAL NOT NULL)"))
        db.execute(text("DELETE FROM robinhood_access_cache"))
        db.commit()
        return {"connected": True, "execution_enabled": False}
    except Exception:
        db.rollback()
        raise


def connection_status(db: Session):
    connection = db.get(BrokerConnection, BROKER)
    authorized = bool(connection and connection.status in {"authorized", "connected"})
    last_check = None
    if authorized:
        last_check = db.scalars(select(AuditLogEntry).where(
            AuditLogEntry.event_type == "broker_read_only_verified",
            AuditLogEntry.timestamp >= connection.connected_at,
        ).order_by(AuditLogEntry.timestamp.desc()).limit(1)).first()
    recently_verified = bool(last_check and (last_check.payload or {}).get("broker") == BROKER
                             and last_check.timestamp >= dt.datetime.utcnow() - dt.timedelta(hours=1))
    return {
        "broker": BROKER,
        # OAuth proves only that the application can refresh a credential. It
        # does not prove the selected account, balances, or permissions.
        "connected": recently_verified,
        "application_authorized": authorized,
        "read_only_ready": recently_verified,
        "execution_enabled": False,
        "connection_time": connection.connected_at if connection else None,
        "last_read_only_verification": last_check.timestamp if last_check else None,
        "reason": ("Dedicated Agentic account was verified read-only within the past hour; execution is disabled."
                   if recently_verified else "Application OAuth is complete; dedicated account verification is still required."
                   if authorized else "Application OAuth has not been completed."),
    }
