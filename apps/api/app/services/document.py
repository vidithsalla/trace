import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import Document, IngestJob
from app.services.evidence_versions import create_document_version
from app.services.storage import storage_service

broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor(actor_name="ingest_document", queue_name="ingestion")
def _ingest_document_message(document_id: str) -> None:  # pragma: no cover - API only enqueues
    raise RuntimeError("API process should not execute ingestion jobs")


@dramatiq.actor(actor_name="run_analysis", queue_name="analysis", max_retries=0, time_limit=15 * 60 * 1000)
def _run_analysis_message(run_id: str) -> None:  # pragma: no cover - API only enqueues
    raise RuntimeError("API process should not execute analysis jobs")


def enqueue_analysis(run_id: UUID) -> None:
    try:
        _run_analysis_message.send(str(run_id))
    except Exception as exc:  # pragma: no cover - defensive queue failure path
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail={"code": "QUEUE_UNAVAILABLE"}) from exc


ALLOWED_UPLOAD_TYPES = {
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "text/plain": {".txt", ".text", ".log"},
    "text/csv": {".csv"},
    "application/csv": {".csv"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
}

SIGNATURES = {
    "application/pdf": (b"%PDF",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (b"PK\x03\x04",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (b"PK\x03\x04",),
}

OCR_CANDIDATE_TYPES = {"application/pdf", "image/png", "image/jpeg"}
CHUNK_SIZE = 1024 * 1024


@dataclass(slots=True)
class PreparedUpload:
    file_name: str
    content_type: str
    file_size_bytes: int
    sha256: str
    storage_key: str
    fileobj: tempfile.SpooledTemporaryFile[bytes]


def _safe_file_name(file_name: str) -> str:
    name = Path(file_name).name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name")
    return name


def _validate_type_and_extension(file_name: str, content_type: str) -> None:
    suffix = Path(file_name).suffix.lower()
    allowed_suffixes = ALLOWED_UPLOAD_TYPES.get(content_type)
    if allowed_suffixes is None or suffix not in allowed_suffixes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")


def _validate_signature(content_type: str, head: bytes) -> None:
    expected = SIGNATURES.get(content_type)
    if expected is None:
        return
    if not any(head.startswith(signature) for signature in expected):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File signature does not match declared type",
        )


async def _prepare_upload(matter_id: UUID, file: UploadFile) -> PreparedUpload:
    if not file.filename or not file.content_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload payload")

    file_name = _safe_file_name(file.filename)
    content_type = file.content_type.split(";")[0].strip().lower()
    _validate_type_and_extension(file_name, content_type)

    hasher = hashlib.sha256()
    total_size = 0
    head = b""
    fileobj = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > settings.max_upload_bytes:
            fileobj.close()
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="File too large")
        if len(head) < 16:
            head += chunk[: 16 - len(head)]
        hasher.update(chunk)
        fileobj.write(chunk)

    if total_size == 0:
        fileobj.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty files are not supported")

    _validate_signature(content_type, head)

    # The key never contains the user-supplied name (kept in the DB), only a sanitized extension.
    suffix = Path(file_name).suffix.lower()
    suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ""
    storage_key = f"matters/{matter_id}/documents/{uuid4().hex}{suffix}"
    return PreparedUpload(
        file_name=file_name,
        content_type=content_type,
        file_size_bytes=total_size,
        sha256=hasher.hexdigest(),
        storage_key=storage_key,
        fileobj=fileobj,
    )


def enqueue_ingest_job(document_id: UUID) -> None:
    try:
        _ingest_document_message.send(str(document_id))
    except Exception as exc:  # pragma: no cover - defensive queue failure path
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to enqueue ingestion job",
        ) from exc


async def queue_document_upload(
    db: Session, matter_id: UUID, user_id: UUID, file: UploadFile
) -> tuple[Document, IngestJob]:
    prepared = await _prepare_upload(matter_id, file)

    try:
        storage_service.upload_fileobj(prepared.storage_key, prepared.fileobj, prepared.content_type)
    finally:
        prepared.fileobj.close()

    document = Document(
        matter_id=matter_id,
        uploaded_by=user_id,
        file_name=prepared.file_name,
        display_name=prepared.file_name,
        mime_type=prepared.content_type,
        file_size_bytes=prepared.file_size_bytes,
        storage_key=prepared.storage_key,
        sha256=prepared.sha256,
        parse_status="uploaded",
        ocr_status="queued" if prepared.content_type in OCR_CANDIDATE_TYPES else "not_needed",
        ingest_status="queued",
        metadata_json={"upload_source": "api", "original_content_type": prepared.content_type},
    )
    db.add(document)
    db.flush()
    create_document_version(
        db, document, storage_key=prepared.storage_key, source_sha256=prepared.sha256,
        file_name=prepared.file_name, mime_type=prepared.content_type,
        file_size_bytes=prepared.file_size_bytes, created_by=user_id,
    )

    ingest_job = IngestJob(
        document_id=document.id,
        matter_id=matter_id,
        status="queued",
        metadata_json={"storage_key": prepared.storage_key, "file_name": prepared.file_name},
    )
    db.add(ingest_job)
    db.flush()

    return document, ingest_job


async def queue_new_document_version(
    db: Session,
    document: Document,
    user_id: UUID,
    file: UploadFile,
    *,
    expected_revision: int,
    change_note: str | None,
):
    """Store a corrected/revised file as a new immutable version of ``document``."""
    from app.models.evidence import DocumentVersion  # local import keeps module load order simple
    from app.services.evidence_versions import next_revision_no

    current_revision = next_revision_no(db, document.id) - 1
    if expected_revision != current_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DOCUMENT_REVISION_CHANGED", "current_revision": current_revision},
        )
    prepared = await _prepare_upload(document.matter_id, file)
    try:
        latest = db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document.id,
            DocumentVersion.revision_no == current_revision,
        ).one_or_none()
        if latest is not None and latest.source_sha256 == prepared.sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "IDENTICAL_CONTENT", "current_revision": current_revision},
            )
        storage_service.upload_fileobj(prepared.storage_key, prepared.fileobj, prepared.content_type)
    finally:
        prepared.fileobj.close()

    version = create_document_version(
        db, document, storage_key=prepared.storage_key, source_sha256=prepared.sha256,
        file_name=prepared.file_name, mime_type=prepared.content_type,
        file_size_bytes=prepared.file_size_bytes, created_by=user_id, change_note=change_note,
    )
    # Legacy (V1) columns mirror the newest upload.
    document.storage_key = prepared.storage_key
    document.sha256 = prepared.sha256
    document.file_size_bytes = prepared.file_size_bytes
    document.mime_type = prepared.content_type
    document.ingest_status = "queued"
    ingest_job = IngestJob(
        document_id=document.id,
        matter_id=document.matter_id,
        status="queued",
        metadata_json={"storage_key": prepared.storage_key, "revision_no": version.revision_no},
    )
    db.add(ingest_job)
    db.flush()
    return version, ingest_job
