from fastapi.testclient import TestClient

from app.main import app
from app.security import dashboard


def test_basic_login_creates_a_dashboard_session_cookie(monkeypatch):
    monkeypatch.setattr(dashboard.settings, "DASHBOARD_PASSWORD", "test-password")
    monkeypatch.setattr(dashboard.settings, "DASHBOARD_COOKIE_SECURE", False)
    with TestClient(app) as client:
        denied = client.get("/dashboard")
        assert denied.status_code == 401

        signed_in = client.get("/dashboard", auth=("operator", "test-password"))
        assert signed_in.status_code == 200
        assert "project100_dashboard" in signed_in.cookies

        # Browser fetches from the dashboard must work without embedding a
        # password in the page URL or JavaScript.
        assert client.get("/paper/status").status_code == 200
