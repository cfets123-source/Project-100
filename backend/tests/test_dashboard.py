from fastapi.testclient import TestClient
import base64

from app.main import app


def test_dashboard_is_read_only_and_identifies_simulation():
    with TestClient(app) as client:
        page = client.get('/dashboard')
        assert page.status_code == 200
        assert 'paper simulation only' in page.text
        assert '/paper/activity' in page.text
        broker = client.get('/brokers/robinhood/status').json()
        assert broker['connected'] is False
        assert broker['execution_enabled'] is False


def test_activity_feed_is_bounded_and_read_only():
    with TestClient(app) as client:
        response = client.get('/paper/activity?limit=1')
        assert response.status_code == 200
        body = response.json()
        assert body['simulated'] is True
        assert len(body['events']) <= 1


def test_dashboard_requires_password_when_configured(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "DASHBOARD_PASSWORD", "test-password")
    with TestClient(app) as client:
        assert client.get('/dashboard').status_code == 401
        token = base64.b64encode(b"operator:test-password").decode()
        assert client.get('/dashboard', headers={"Authorization": f"Basic {token}"}).status_code == 200
        assert client.get('/brokers/robinhood/connect').status_code == 401
