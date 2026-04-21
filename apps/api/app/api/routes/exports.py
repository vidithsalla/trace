from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.domain import ExportJob
from app.schemas.export import ExportJobRead
from app.services.audit import record_audit_event
from app.services.exports import export_download_payload
from app.services.matter import ensure_matter_access

router = APIRouter()


@router.get("/exports/{export_id}", response_model=ExportJobRead)
def get_export_job(
    export_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> ExportJobRead:
    export_job = db.get(ExportJob, export_id)
    if export_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    ensure_matter_access(db, export_job.matter_id, current_user)
    download_url = f"/exports/{export_job.id}/download" if export_job.status == "completed" else None
    return ExportJobRead.model_validate(export_job).model_copy(update={"download_url": download_url})


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> Response:
    export_job = db.get(ExportJob, export_id)
    if export_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    ensure_matter_access(db, export_job.matter_id, current_user)
    try:
        artifact = export_download_payload(db, export_job)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=export_job.matter_id,
        action="export_download",
        target_type="export_job",
        target_id=export_job.id,
        metadata={"export_type": export_job.export_type, "file_name": artifact.file_name},
    )
    db.commit()
    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={"content-disposition": f'attachment; filename="{artifact.file_name}"'},
    )
