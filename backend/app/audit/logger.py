from sqlalchemy.orm import Session
from app.db.transactions import persist
from app.models.models import AuditLogEntry


def log_event(db: Session, event_type: str, payload: dict, actor: str = "system") -> AuditLogEntry:
    """Append-only audit event. Caller is responsible for committing (or use log_and_commit)."""
    entry = AuditLogEntry(event_type=event_type, payload=payload, actor=actor)
    db.add(entry)
    return entry


def log_and_commit(db: Session, event_type: str, payload: dict, actor: str = "system") -> AuditLogEntry:
    entry = log_event(db, event_type, payload, actor)
    persist(db)
    db.refresh(entry)
    return entry
