import csv
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.domain import AuditLog
from app.schemas.audit import AuditLogRead

router = APIRouter()


@router.get("/audit", response_model=list[AuditLogRead])
def list_audit_logs(
    matter_id: UUID | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.organization_id == current_user.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if matter_id is not None:
        stmt = stmt.where(AuditLog.matter_id == matter_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    return list(db.scalars(stmt))


@router.get("/audit/export.csv")
def export_audit_csv(
    matter_id: UUID | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    logs = list_audit_logs(matter_id=matter_id, limit=limit, db=db, current_user=current_user)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "created_at",
            "organization_id",
            "user_id",
            "matter_id",
            "action",
            "target_type",
            "target_id",
            "metadata_json",
        ]
    )
    for log in logs:
        writer.writerow(
            [
                log.created_at.isoformat(),
                log.organization_id,
                log.user_id or "",
                log.matter_id or "",
                log.action,
                log.target_type or "",
                log.target_id or "",
                log.metadata_json,
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": 'attachment; filename="trace-audit.csv"'},
    )
