"""Audit log helper."""
from sqlalchemy.orm import Session
from app.models import AuditLog


def log_audit(
    db: Session,
    user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    before_data: dict | None = None,
    after_data: dict | None = None,
):
    """Create an audit log entry. Does not commit — caller must commit."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_data=before_data,
        after_data=after_data,
    )
    db.add(entry)
    return entry
