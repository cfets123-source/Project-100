from unittest.mock import Mock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.robinhood_mcp import RobinhoodMcpError, discover_capabilities
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


@patch("app.brokers.robinhood_mcp.httpx.post")
def test_capability_discovery_only_lists_tools(post, db):
    key = Fernet.generate_key().decode()
    db.add(BrokerConnection(broker=BROKER, client_id="client", encrypted_refresh_token=
                            Fernet(key.encode()).encrypt(b"refresh").decode()))
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
