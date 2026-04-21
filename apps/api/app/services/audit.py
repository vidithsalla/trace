from uuid import UUID

from sqlalchemy.orm import Session

from app.models.domain import AuditLog


def record_audit_event(
    db: Session,
    organization_id: UUID,
    action: str,
    user_id: UUID | None = None,
    matter_id: UUID | None = None,
    target_type: str | None = None,
    target_id: UUID | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    event = AuditLog(
        organization_id=organization_id,
        user_id=user_id,
        matter_id=matter_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_json=metadata or {},
    )
    db.add(event)
    return event
