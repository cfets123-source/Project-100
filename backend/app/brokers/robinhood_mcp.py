"""Discovery-only transport for Robinhood's Trading MCP.

This module deliberately supports only the MCP handshake and ``tools/list``.
It contains no ``tools/call`` method, so an application OAuth connection cannot
be mistaken for permission to inspect accounts, preview orders, or trade.
"""
import contextlib
import fcntl
import json
import os
import tempfile
import time
import uuid
from typing import Optional

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.brokers.robinhood_oauth import (BROKER, MCP_URL, TOKEN_URL,
                                         BrokerOAuthConfigurationError, _fernet)
from app.audit.logger import log_and_commit
from app.models.models import BrokerConnection

MCP_PROTOCOL_VERSION = "2025-03-26"


class RobinhoodMcpError(RuntimeError):
    """A safe-to-display connection error; never include credentials."""


def _jsonrpc_response(response: httpx.Response) -> dict:
    """Decode a JSON-RPC response, including a single SSE data frame."""
    response.raise_for_status()
    text = response.text.strip()
    if "text/event-stream" in response.headers.get("content-type", "") or text.startswith(("event:", "data:")):
        frames = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        if not frames:
            raise RobinhoodMcpError("Robinhood MCP returned an empty event stream")
        text = frames[0]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RobinhoodMcpError("Robinhood MCP returned an unreadable response") from exc
    if not isinstance(payload, dict):
        raise RobinhoodMcpError("Robinhood MCP returned an invalid response")
    if "error" in payload:
        raise RobinhoodMcpError("Robinhood MCP rejected the read-only capability check")
    return payload


class RobinhoodMcpDiscoveryClient:
    """A short-lived authenticated session that only discovers MCP tools."""

    def __init__(self, access_token: str):
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        self._session_id = None
        self._initialized = False

    def _request(self, method: str, params: Optional[dict] = None, notification: bool = False) -> dict:
        body = {"jsonrpc": "2.0", "method": method}
        if not notification:
            body["id"] = str(uuid.uuid4())
        if params is not None:
            body["params"] = params
        headers = dict(self._headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        response = httpx.post(MCP_URL, headers=headers, json=body, timeout=15)
        if notification:
            response.raise_for_status()
            return {}
        payload = _jsonrpc_response(response)
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            payload["_headers"] = {"mcp-session-id": session_id}
        return payload

    def _initialize(self) -> None:
        if self._initialized:
            return
        result = self._request("initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "Project 100", "version": "0.1.0"},
        })
        session_id = result.get("_headers", {}).get("mcp-session-id")
        # httpx headers are attached before parsing where available. The fallback
        # permits simple mocked JSON-RPC tests without inventing a server header.
        if session_id:
            self._session_id = session_id
        self._request("notifications/initialized", notification=True)
        self._initialized = True

    def list_tools(self) -> list[dict]:
        """Return only public tool metadata. No account or order action occurs."""
        self._initialize()
        payload = self._request("tools/list")
        tools = payload.get("result", {}).get("tools")
        if not isinstance(tools, list):
            raise RobinhoodMcpError("Robinhood MCP did not return a tool list")
        safe_tools = []
        for tool in tools:
            if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                safe_tools.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {}),
                })
        return safe_tools


_CACHE_DDL = ("CREATE TABLE IF NOT EXISTS robinhood_access_cache "
              "(id TEXT PRIMARY KEY, token TEXT NOT NULL, expires_at REAL NOT NULL)")
_LOCK_PATH = os.environ.get("ROBINHOOD_TOKEN_LOCK", "/data/.robinhood-token.lock")


@contextlib.contextmanager
def _refresh_lock():
    """One refresh at a time across every container sharing /data.

    Robinhood rotates the refresh token on use. Two workers refreshing with the
    same stored token at once makes the second one present an already-used token,
    which the broker treats as reuse and revokes, i.e. the account "disconnects".
    """
    path = _LOCK_PATH if os.path.isdir(os.path.dirname(_LOCK_PATH)) else os.path.join(
        tempfile.gettempdir(), "robinhood-token.lock")
    with open(path, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _cached_access_token(db: Session, fernet) -> str | None:
    db.execute(text(_CACHE_DDL))
    row = db.execute(text("SELECT token, expires_at FROM robinhood_access_cache WHERE id = :i"),
                     {"i": BROKER}).first()
    if row and row[1] > time.time() + 60:
        try:
            return fernet.decrypt(row[0].encode()).decode()
        except (InvalidToken, UnicodeDecodeError):
            return None
    return None


def _access_token(db: Session, encryption_key: str) -> str:
    fernet = _fernet(encryption_key)
    cached = _cached_access_token(db, fernet)
    if cached:
        return cached
    with _refresh_lock():
        db.expire_all()  # another container may have refreshed while we waited
        cached = _cached_access_token(db, fernet)
        if cached:
            db.commit()
            return cached
        connection = db.get(BrokerConnection, BROKER)
        # OAuth completion records "authorized" first. Capability discovery is the
        # next safe, read-only step; it must not require a fictional prior state.
        if connection is None or connection.status not in {"authorized", "connected"}:
            raise RobinhoodMcpError("Application OAuth has not been completed.")
        try:
            refresh_token = fernet.decrypt(connection.encrypted_refresh_token.encode()).decode()
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise RobinhoodMcpError("Stored broker authorization cannot be decrypted") from exc
        response = httpx.post(TOKEN_URL, data={
            "grant_type": "refresh_token", "client_id": connection.client_id,
            "refresh_token": refresh_token,
        }, timeout=15)
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise RobinhoodMcpError("Robinhood did not return an access token")
        rotated = payload.get("refresh_token")
        if isinstance(rotated, str) and rotated:
            connection.encrypted_refresh_token = fernet.encrypt(rotated.encode()).decode()
            db.add(connection)
        lifetime = payload.get("expires_in")
        lifetime = float(lifetime) if isinstance(lifetime, (int, float)) and lifetime > 0 else 300.0
        db.execute(text("INSERT OR REPLACE INTO robinhood_access_cache (id, token, expires_at) "
                        "VALUES (:i, :t, :e)"),
                   {"i": BROKER, "t": fernet.encrypt(token.encode()).decode(),
                    "e": time.time() + lifetime})
        db.commit()
        return token


def discover_capabilities(db: Session, encryption_key: str) -> dict:
    """Refresh a token then list broker-declared tools. It never calls a tool."""
    try:
        tools = RobinhoodMcpDiscoveryClient(_access_token(db, encryption_key)).list_tools()
    except BrokerOAuthConfigurationError:
        raise
    except httpx.HTTPError as exc:
        raise RobinhoodMcpError("Robinhood capability check could not reach the broker") from exc
    # Preserve evidence that discovery happened, but retain neither credentials
    # nor broker output beyond names/count. Tool descriptions and schemas can be
    # arbitrary server content and do not belong in the audit event.
    log_and_commit(db, "broker_capability_discovered", {
        "broker": BROKER, "tool_count": len(tools),
        "tool_names": [tool["name"] for tool in tools],
        "discovery_only": True, "execution_enabled": False,
    })
    return {"broker": BROKER, "discovery_only": True, "execution_enabled": False, "tools": tools}
