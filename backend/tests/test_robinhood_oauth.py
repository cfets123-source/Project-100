import base64
from unittest.mock import Mock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.robinhood_oauth import (BrokerOAuthConfigurationError, finish_connection,
                                         start_connection, connection_status)
from app.db.session import Base
from app.models import models  # noqa: F401 registers all tables
from app.models.models import BrokerConnection, BrokerOAuthState


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_oauth_requires_https_callback(db):
    with pytest.raises(BrokerOAuthConfigurationError):
        start_connection(db, "http://localhost/callback")


@patch("app.brokers.robinhood_oauth.httpx.post")
def test_oauth_pkce_and_encrypted_refresh_token(post, db):
    post.return_value = Mock(raise_for_status=Mock(), json=lambda: {"client_id": "registered-client"})
    url = start_connection(db, "https://project100.example/callback")
    state = url.split("state=")[1].split("&")[0]
    pending = db.get(BrokerOAuthState, state)
    assert pending and "code_challenge=" in url and pending.code_verifier not in url
    post.return_value = Mock(raise_for_status=Mock(), json=lambda: {"refresh_token": "secret-refresh"})
    key = Fernet.generate_key().decode()
    result = finish_connection(db, state, "authorization-code", "https://project100.example/callback", key)
    saved = db.get(BrokerConnection, "robinhood_agentic_trading")
    assert result == {"connected": True, "execution_enabled": False}
    assert saved.encrypted_refresh_token != "secret-refresh"
    assert saved.status == "authorized"
    assert connection_status(db)["connected"] is False
    assert connection_status(db)["application_authorized"] is True
    assert db.get(BrokerOAuthState, state) is None
