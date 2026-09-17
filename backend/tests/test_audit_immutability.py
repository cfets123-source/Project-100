import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import AuditLogEntry, AuditImmutabilityError
from app.audit.logger import log_and_commit


@pytest.fixture
def engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


def test_audit_row_cannot_be_updated(engine):
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    entry = log_and_commit(db, "test_event", {"a": 1})
    entry.event_type = "tampered"
    with pytest.raises(AuditImmutabilityError):
        db.commit()
    db.rollback()


def test_audit_row_cannot_be_deleted(engine):
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    entry = log_and_commit(db, "test_event", {"a": 1})
    db.delete(entry)
    with pytest.raises(AuditImmutabilityError):
        db.commit()
    db.rollback()


def test_audit_rows_survive_new_session_against_same_engine(engine):
    """Proxy for restart-persistence: a fresh Session bound to the same underlying
    engine (as would happen after a process restart against a real, persistent
    database file) still sees prior rows."""
    Base.metadata.create_all(bind=engine)
    db1 = sessionmaker(bind=engine)()
    log_and_commit(db1, "before_restart", {"x": 1})
    db1.close()

    db2 = sessionmaker(bind=engine)()
    rows = db2.query(AuditLogEntry).filter(AuditLogEntry.event_type == "before_restart").all()
    assert len(rows) == 1


def test_audit_write_failure_is_not_swallowed(engine):
    """If the audit commit itself fails (e.g. a non-serializable payload slips
    through), callers must see the exception rather than having it silently
    swallowed — a caller (e.g. ExecutionGateway) that logs risk_decision before
    calling the broker will therefore abort instead of proceeding unaudited."""
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    class Unserializable:
        pass

    with pytest.raises(Exception):
        log_and_commit(db, "should_fail", {"bad": Unserializable()})
