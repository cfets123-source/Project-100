from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.audit.logger import log_and_commit
from app.models.models import AuditLogEntry

client = TestClient(app)


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["trading_mode"] == "paper"
    assert body["autonomy_level"] == 0  # LEVEL_0_RESEARCH_ONLY default


def test_system_state_endpoint_defaults_to_off():
    r = client.get("/system/state")
    assert r.status_code == 200
    assert r.json()["state"] == "off"


def test_risk_config_endpoint_reflects_safe_defaults():
    r = client.get("/config/risk")
    body = r.json()
    assert body["ALLOW_MARGIN"] is False
    assert body["ALLOW_OPTIONS"] is False
    assert body["ALLOW_SHORTS"] is False
    assert body["ALLOW_LEVERAGE"] is False
    assert body["AUTO_EXECUTION"] is False


def test_audit_log_is_append_only_write():
    db = SessionLocal()
    before = db.query(AuditLogEntry).count()
    log_and_commit(db, "config_change", {"field": "MAX_RISK_PER_TRADE", "old": 0.01, "new": 0.01})
    after = db.query(AuditLogEntry).count()
    assert after == before + 1
    db.close()
