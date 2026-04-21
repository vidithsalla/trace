from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.domain import ExportJob, Matter, Memo, utcnow
from app.services.audit import record_audit_event
from app.services.chronology import list_chronology_events, render_chronology_csv, render_chronology_docx
from app.services.memos import render_memo_docx, render_memo_markdown
from app.services.storage import storage_service


@dataclass(slots=True)
class ExportArtifact:
    content: bytes
    content_type: str
    file_name: str
    extension: str


def create_export_job(
    db: Session,
    *,
    matter_id: UUID,
    requested_by: UUID,
    organization_id: UUID,
    export_type: str,
    source_object_type: str,
    source_object_id: UUID,
    metadata: dict | None = None,
) -> ExportJob:
    export_job = ExportJob(
        matter_id=matter_id,
        requested_by=requested_by,
        export_type=export_type,
        status="queued",
        source_object_type=source_object_type,
        source_object_id=source_object_id,
        metadata_json=metadata or {},
    )
    db.add(export_job)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=requested_by,
        matter_id=matter_id,
        action="export_job_queued",
        target_type="export_job",
        target_id=export_job.id,
        metadata={"export_type": export_type, "source_object_type": source_object_type},
    )
    return export_job


def process_export_job(db: Session, export_job_id: UUID) -> ExportArtifact:
    export_job = db.get(ExportJob, export_job_id)
    if export_job is None:
        raise ValueError("Export job not found")
    matter = db.get(Matter, export_job.matter_id)
    if matter is None:
        raise ValueError("Export matter not found")

    started_at = utcnow()
    export_job.status = "running"
    export_job.error_message = None
    export_job.metadata_json = {
        **(export_job.metadata_json or {}),
        "started_at": started_at.isoformat(),
    }
    record_audit_event(
        db,
        organization_id=matter.organization_id,
        user_id=export_job.requested_by,
        matter_id=export_job.matter_id,
        action="export_job_started",
        target_type="export_job",
        target_id=export_job.id,
        metadata={"export_type": export_job.export_type},
    )
    db.flush()

    try:
        artifact = build_export_artifact(db, export_job)
        storage_key = f"exports/{export_job.matter_id}/{export_job.id}.{artifact.extension}"
        storage_service.upload_fileobj(storage_key, BytesIO(artifact.content), artifact.content_type)
        finished_at = utcnow()
        export_job.status = "completed"
        export_job.storage_key = storage_key
        export_job.error_message = None
        export_job.metadata_json = {
            **(export_job.metadata_json or {}),
            "content_type": artifact.content_type,
            "file_name": artifact.file_name,
            "size_bytes": len(artifact.content),
            "finished_at": finished_at.isoformat(),
            "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
        }
        record_audit_event(
            db,
            organization_id=matter.organization_id,
            user_id=export_job.requested_by,
            matter_id=export_job.matter_id,
            action="export_job_completed",
            target_type="export_job",
            target_id=export_job.id,
            metadata={
                "export_type": export_job.export_type,
                "storage_key": storage_key,
                "size_bytes": len(artifact.content),
            },
        )
        db.flush()
        return artifact
    except Exception as exc:
        export_job.status = "failed"
        export_job.error_message = exc.__class__.__name__
        export_job.metadata_json = {
            **(export_job.metadata_json or {}),
            "failed_at": utcnow().isoformat(),
        }
        record_audit_event(
            db,
            organization_id=matter.organization_id,
            user_id=export_job.requested_by,
            matter_id=export_job.matter_id,
            action="export_job_failed",
            target_type="export_job",
            target_id=export_job.id,
            metadata={"export_type": export_job.export_type, "error_class": exc.__class__.__name__},
        )
        db.flush()
        raise


def create_completed_export(
    db: Session,
    *,
    matter_id: UUID,
    requested_by: UUID,
    organization_id: UUID,
    export_type: str,
    source_object_type: str,
    source_object_id: UUID,
    metadata: dict | None = None,
) -> tuple[ExportJob, ExportArtifact]:
    export_job = create_export_job(
        db,
        matter_id=matter_id,
        requested_by=requested_by,
        organization_id=organization_id,
        export_type=export_type,
        source_object_type=source_object_type,
        source_object_id=source_object_id,
        metadata=metadata,
    )
    artifact = process_export_job(db, export_job.id)
    return export_job, artifact


def build_export_artifact(db: Session, export_job: ExportJob) -> ExportArtifact:
    if export_job.export_type == "memo_markdown":
        memo = _memo_for_export(db, export_job)
        content = (memo.content_markdown or render_memo_markdown(memo.content_json)).encode("utf-8")
        return ExportArtifact(content, "text/markdown", "trace-memo.md", "md")

    if export_job.export_type == "memo_docx":
        memo = _memo_for_export(db, export_job)
        return ExportArtifact(
            render_memo_docx(memo.content_json),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "trace-memo.docx",
            "docx",
        )

    if export_job.export_type == "chronology_csv":
        events = list_chronology_events(db, export_job.matter_id)
        return ExportArtifact(
            render_chronology_csv(events).encode("utf-8"),
            "text/csv",
            "trace-chronology.csv",
            "csv",
        )

    if export_job.export_type == "chronology_docx":
        events = list_chronology_events(db, export_job.matter_id)
        return ExportArtifact(
            render_chronology_docx(events),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "trace-chronology.docx",
            "docx",
        )

    raise ValueError(f"Unsupported export type: {export_job.export_type}")


def export_download_payload(db: Session, export_job: ExportJob) -> ExportArtifact:
    if export_job.status != "completed" or not export_job.storage_key:
        raise ValueError("Export is not ready for download")
    metadata = export_job.metadata_json or {}
    content_type = metadata.get("content_type") or "application/octet-stream"
    file_name = metadata.get("file_name") or f"trace-export-{export_job.id}"
    extension = file_name.rsplit(".", maxsplit=1)[-1] if "." in file_name else "bin"
    return ExportArtifact(
        storage_service.get_object_bytes(export_job.storage_key),
        content_type,
        file_name,
        extension,
    )


def _memo_for_export(db: Session, export_job: ExportJob) -> Memo:
    memo = db.get(Memo, export_job.source_object_id)
    if memo is None or memo.matter_id != export_job.matter_id:
        raise ValueError("Memo export source not found")
    return memo
