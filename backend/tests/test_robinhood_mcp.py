from unittest.mock import Mock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.robinhood_mcp import RobinhoodMcpError, _access_token, _jsonrpc_response, discover_capabilities
from app.brokers.robinhood_oauth import BROKER
from app.db.session import Base
from app.models import models  # noqa: F401 registers all tables
from app.models.models import BrokerConnection
from app.models.models import AuditLogEntry


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _response(payload):
    return Mock(text=__import__("json").dumps(payload), raise_for_status=Mock(), headers={})


def test_standard_sse_event_is_decoded():
    response = Mock(text='event: message\ndata: {"jsonrpc":"2.0","id":"1","result":{"ok":true}}\n\n',
                    raise_for_status=Mock(), headers={"content-type": "text/event-stream"})
    assert _jsonrpc_response(response)["result"]["ok"] is True


@patch("app.brokers.robinhood_mcp.httpx.post")
def test_capability_discovery_only_lists_tools(post, db):
    key = Fernet.generate_key().decode()
    db.add(BrokerConnection(broker=BROKER, client_id="client", encrypted_refresh_token=
                            Fernet(key.encode()).encrypt(b"refresh").decode(), status="authorized"))
    db.commit()
    post.side_effect = [
        Mock(raise_for_status=Mock(), json=lambda: {"access_token": "access"}),
        _response({"jsonrpc": "2.0", "result": {"protocolVersion": "2025-03-26"}}),
        Mock(raise_for_status=Mock()),
        _response({"jsonrpc": "2.0", "result": {"tools": [
            {"name": "accounts_list", "description": "metadata", "inputSchema": {}},
        ]}}),
    ]
    result = discover_capabilities(db, key)
    assert result["execution_enabled"] is False
    assert result["tools"][0]["name"] == "accounts_list"
    audit = db.query(AuditLogEntry).one()
    assert audit.event_type == "broker_capability_discovered"
    assert audit.payload["tool_names"] == ["accounts_list"]
    assert "access" not in str(audit.payload)
    methods = [call.kwargs.get("json", {}).get("method") for call in post.call_args_list]
    assert methods == [None, "initialize", "notifications/initialized", "tools/list"]
    assert "tools/call" not in methods


def test_capability_discovery_requires_connection(db):
    with pytest.raises(RobinhoodMcpError, match="OAuth"):
        discover_capabilities(db, Fernet.generate_key().decode())


@patch("app.brokers.robinhood_mcp.httpx.post")
def test_rotated_refresh_token_is_saved_encrypted(post, db):
    key = Fernet.generate_key().decode()
    old = Fernet(key.encode()).encrypt(b"old-refresh").decode()
    db.add(BrokerConnection(broker=BROKER, client_id="client",
                            encrypted_refresh_token=old, status="authorized"))
    db.commit()
    post.return_value = Mock(raise_for_status=Mock(),
                             json=lambda: {"access_token": "access", "refresh_token": "new-refresh"})
    assert _access_token(db, key) == "access"
    row = db.get(BrokerConnection, BROKER)
    assert row.encrypted_refresh_token != old
    assert Fernet(key.encode()).decrypt(row.encrypted_refresh_token.encode()) == b"new-refresh"


@patch("app.brokers.robinhood_mcp.httpx.post")
def test_access_token_is_cached_so_workers_do_not_refresh_repeatedly(post, db):
    key = Fernet.generate_key().decode()
    db.add(BrokerConnection(broker=BROKER, client_id="client", status="authorized",
                            encrypted_refresh_token=Fernet(key.encode()).encrypt(b"r1").decode()))
    db.commit()
    post.return_value = Mock(raise_for_status=Mock(), json=lambda: {
        "access_token": "a1", "refresh_token": "r2", "expires_in": 3600})
    assert [_access_token(db, key) for _ in range(5)] == ["a1"] * 5
    assert post.call_count == 1  # one refresh, then the shared cache is reused


@patch("app.brokers.robinhood_mcp.httpx.post")
def test_expired_cache_refreshes_with_latest_rotated_token(post, db, monkeypatch):
    import app.brokers.robinhood_mcp as mcp
    key = Fernet.generate_key().decode()
    db.add(BrokerConnection(broker=BROKER, client_id="client", status="authorized",
                            encrypted_refresh_token=Fernet(key.encode()).encrypt(b"r1").decode()))
    db.commit()
    sent = []
    def reply(url, data, timeout):
        sent.append(data["refresh_token"])
        n = len(sent)
        return Mock(raise_for_status=Mock(), json=lambda: {
            "access_token": f"a{n}", "refresh_token": f"r{n + 1}", "expires_in": 30})
    post.side_effect = reply
    _access_token(db, key)
    _access_token(db, key)  # 30s lifetime is inside the 60s safety margin -> refresh again
    assert sent == ["r1", "r2"]  # never re-uses a rotated (spent) refresh token
