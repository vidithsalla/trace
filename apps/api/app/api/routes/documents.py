from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.domain import Document, DocumentPage
from app.schemas.document import DocumentDetail, DocumentListItem, DocumentPageRead
from app.services.audit import record_audit_event
from app.services.document import (
    enqueue_ingest_job,
    queue_document_upload,
    queue_new_document_version,
)
from app.services.matter import WRITE_ROLES, ensure_matter_access, ensure_matter_role
from app.services.storage import storage_service

router = APIRouter()


@router.post("/matters/{matter_id}/documents/upload", response_model=DocumentDetail)
async def upload_document(
    matter_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Document:
    ensure_matter_access(db, matter_id, current_user)
    upload_metadata = {"file_name": file.filename, "content_type": file.content_type}
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=matter_id,
        action="upload_document_started",
        target_type="document",
        metadata=upload_metadata,
    )

    try:
        document, ingest_job = await queue_document_upload(db, matter_id, current_user.id, file)
    except HTTPException as exc:
        record_audit_event(
            db,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            matter_id=matter_id,
            action="upload_document_failed",
            target_type="document",
            metadata={**upload_metadata, "status_code": exc.status_code, "detail": exc.detail},
        )
        db.commit()
        raise

    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=matter_id,
        action="upload_document",
        target_type="document",
        target_id=document.id,
        metadata={
            "file_name": document.file_name,
            "mime_type": document.mime_type,
            "ingest_job_id": str(ingest_job.id),
        },
    )
    db.commit()
    try:
        enqueue_ingest_job(document.id)
    except HTTPException as exc:
        document.ingest_status = "failed"
        document.error_message = exc.detail
        ingest_job.status = "failed"
        ingest_job.error_message = exc.detail
        record_audit_event(
            db,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            matter_id=matter_id,
            action="upload_document_enqueue_failed",
            target_type="ingest_job",
            target_id=ingest_job.id,
            metadata={**upload_metadata, "document_id": str(document.id), "detail": exc.detail},
        )
        db.commit()
        raise
    db.refresh(document)
    return document


@router.get("/matters/{matter_id}/documents", response_model=list[DocumentListItem])
def list_documents(
    matter_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> list[Document]:
    ensure_matter_access(db, matter_id, current_user)
    stmt = select(Document).where(Document.matter_id == matter_id).order_by(Document.created_at.desc())
    return list(db.scalars(stmt))


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    ensure_matter_access(db, document.matter_id, current_user)
    return document


@router.get("/documents/{document_id}/file")
def get_document_file(
    document_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> Response:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    ensure_matter_access(db, document.matter_id, current_user)
    try:
        content = storage_service.get_object_bytes(document.storage_key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found"
        ) from exc
    safe_file_name = document.file_name.replace('"', "")
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=document.matter_id,
        action="view_document_file",
        target_type="document",
        target_id=document.id,
        metadata={"file_name": document.file_name, "mime_type": document.mime_type},
    )
    db.commit()
    return Response(
        content=content,
        media_type=document.mime_type,
        headers={"content-disposition": f'inline; filename="{safe_file_name}"'},
    )


@router.get("/documents/{document_id}/pages/{page_number}", response_model=DocumentPageRead)
def get_document_page(
    document_id: UUID,
    page_number: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> DocumentPage:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    ensure_matter_access(db, document.matter_id, current_user)
    stmt = select(DocumentPage).where(
        DocumentPage.document_id == document_id, DocumentPage.page_number == page_number
    )
    page = db.scalar(stmt)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=document.matter_id,
        action="view_document_page",
        target_type="document_page",
        target_id=page.id,
        metadata={"document_id": str(document.id), "page_number": page_number},
    )
    db.commit()
    return page


@router.post("/matters/{matter_id}/documents/{document_id}/versions", status_code=202)
async def upload_document_version(
    matter_id: UUID,
    document_id: UUID,
    file: UploadFile = File(...),
    expected_revision: int = Form(...),
    change_note: str | None = Form(None, max_length=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Upload a corrected or revised file as a new immutable version of an existing document."""
    ensure_matter_role(db, matter_id, current_user, WRITE_ROLES)
    document = db.get(Document, document_id)
    if document is None or document.matter_id != matter_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    version, ingest_job = await queue_new_document_version(
        db, document, current_user.id, file,
        expected_revision=expected_revision, change_note=change_note,
    )
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=matter_id,
        action="upload_document_version",
        target_type="document",
        target_id=document.id,
        metadata={"revision_no": version.revision_no, "version_id": str(version.id)},
    )
    db.commit()
    try:
        enqueue_ingest_job(document.id)
    except HTTPException:
        ingest_job.status = "failed"
        db.commit()
        raise
    return {"document_id": str(document.id), "version_id": str(version.id),
            "revision_no": version.revision_no, "state": version.state}
