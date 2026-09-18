from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_insights_are_explicitly_simulated_and_read_only():
    with TestClient(app) as client:
        response = client.get("/paper/insights")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper"
    assert body["simulated"] is True
    assert set(body) >= {"equity_curve", "closed_trades", "strategy_breakdown", "risk_events"}
