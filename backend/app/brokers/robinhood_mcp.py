"""Discovery-only transport for Robinhood's Trading MCP.

This module deliberately supports only the MCP handshake and ``tools/list``.
It contains no ``tools/call`` method, so an application OAuth connection cannot
be mistaken for permission to inspect accounts, preview orders, or trade.
"""
import json
import uuid
from typing import Optional

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.brokers.robinhood_oauth import (BROKER, MCP_URL, TOKEN_URL,
                                         BrokerOAuthConfigurationError, _fernet)
from app.models.models import BrokerConnection

MCP_PROTOCOL_VERSION = "2025-03-26"


class RobinhoodMcpError(RuntimeError):
    """A safe-to-display connection error; never include credentials."""


def _jsonrpc_response(response: httpx.Response) -> dict:
    """Decode a JSON-RPC response, including a single SSE data frame."""
    response.raise_for_status()
    text = response.text.strip()
    if text.startswith("data:"):
        text = text.split("data:", 1)[1].strip().split("\n\n", 1)[0]
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


def _access_token(db: Session, encryption_key: str) -> str:
    connection = db.get(BrokerConnection, BROKER)
    if connection is None or connection.status != "connected":
        raise RobinhoodMcpError("Application OAuth has not been completed.")
    try:
        refresh_token = _fernet(encryption_key).decrypt(connection.encrypted_refresh_token.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RobinhoodMcpError("Stored broker authorization cannot be decrypted") from exc
    response = httpx.post(TOKEN_URL, data={
        "grant_type": "refresh_token", "client_id": connection.client_id,
        "refresh_token": refresh_token,
    }, timeout=15)
    response.raise_for_status()
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise RobinhoodMcpError("Robinhood did not return an access token")
    return token


def discover_capabilities(db: Session, encryption_key: str) -> dict:
    """Refresh a token then list broker-declared tools. It never calls a tool."""
    try:
        tools = RobinhoodMcpDiscoveryClient(_access_token(db, encryption_key)).list_tools()
    except BrokerOAuthConfigurationError:
        raise
    except httpx.HTTPError as exc:
        raise RobinhoodMcpError("Robinhood capability check could not reach the broker") from exc
    return {"broker": BROKER, "discovery_only": True, "execution_enabled": False, "tools": tools}
