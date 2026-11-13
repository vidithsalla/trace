from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain import Document, DocumentChunk, DocumentPage, IngestJob, Matter, utcnow
from app.services.audit import record_audit_event
from app.services.embeddings import get_embedding_client
from app.services.entities import extract_entities_for_matter
from app.services.evidence_versions import (
    PageText,
    parser_profile,
    pending_version_for,
    publish_extraction,
)
from app.services.parsers import ParsedPage, get_parser
from app.services.storage import storage_service

TARGET_CHUNK_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 150


@dataclass(slots=True)
class ChunkDraft:
    page_start: int
    page_end: int
    chunk_index: int
    text: str
    token_count: int
    metadata: dict


def chunk_pages(
    pages: list[ParsedPage],
    *,
    target_tokens: int = TARGET_CHUNK_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    chunk_index = 0
    step = max(target_tokens - overlap_tokens, 1)

    for page in pages:
        words = page.normalized_text.split()
        if not words:
            continue

        start = 0
        while start < len(words):
            end = min(start + target_tokens, len(words))
            chunk_words = words[start:end]
            chunks.append(
                ChunkDraft(
                    page_start=page.page_number,
                    page_end=page.page_number,
                    chunk_index=chunk_index,
                    text=" ".join(chunk_words),
                    token_count=len(chunk_words),
                    metadata={
                        "page_number": page.page_number,
                        "word_start": start,
                        "word_end": end,
                        "target_tokens": target_tokens,
                        "overlap_tokens": overlap_tokens if start > 0 else 0,
                    },
                )
            )
            chunk_index += 1
            if end == len(words):
                break
            start += step

    return chunks


def process_document(db: Session, document_id: UUID) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError("Document not found")

    ingest_job = _start_ingest_job(db, document)
    version = pending_version_for(db, document)
    content = storage_service.get_object_bytes(version.storage_key)
    if version.source_sha256 and hashlib.sha256(content).hexdigest() != version.source_sha256:
        raise ValueError("stored bytes do not match the version's SHA-256")
    parser = get_parser(version.mime_type, version.file_name)
    parse_result = parser.parse(content, file_name=version.file_name)
    publish_extraction(
        db,
        version,
        [PageText(page.page_number, page.normalized_text) for page in parse_result.pages],
        profile=parser_profile(type(parser).__name__),
        warnings=[] if parse_result.parse_status == "completed" else [f"PARSE_{parse_result.parse_status.upper()}"],
    )

    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    db.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))

    for page in parse_result.pages:
        db.add(
            DocumentPage(
                document_id=document.id,
                page_number=page.page_number,
                raw_text=page.raw_text,
                normalized_text=page.normalized_text,
                image_storage_key=page.image_storage_key,
                ocr_confidence=page.ocr_confidence,
                has_text_layer=page.has_text_layer,
                metadata_json=page.metadata,
            )
        )

    chunk_drafts = chunk_pages(parse_result.pages)
    embeddings = get_embedding_client().embed_texts(chunk.text for chunk in chunk_drafts)
    for chunk, embedding in zip(chunk_drafts, embeddings, strict=True):
        db.add(
            DocumentChunk(
                document_id=document.id,
                matter_id=document.matter_id,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                token_count=chunk.token_count,
                embedding=embedding,
                metadata_json=chunk.metadata,
            )
        )
    db.flush()
    extracted_entities = extract_entities_for_matter(
        db,
        document.matter_id,
        document.uploaded_by,
        document_ids=[document.id],
        summarize=False,
    )

    document.page_count = len(parse_result.pages)
    document.parse_status = parse_result.parse_status
    document.ocr_status = parse_result.ocr_status
    document.ingest_status = "completed"
    document.extraction_quality_score = parse_result.extraction_quality_score
    document.error_message = None
    document.metadata_json = {
        **(document.metadata_json or {}),
        "parser": parse_result.metadata,
        "chunk_count": len(chunk_drafts),
        "entity_count": len(extracted_entities),
    }

    ingest_job.status = "completed"
    ingest_job.finished_at = utcnow()
    ingest_job.error_message = None
    ingest_job.metadata_json = {
        **(ingest_job.metadata_json or {}),
        "page_count": len(parse_result.pages),
        "chunk_count": len(chunk_drafts),
        "ocr_status": parse_result.ocr_status,
        "entity_count": len(extracted_entities),
    }
    record_audit_event(
        db,
        organization_id=_organization_id_for_document(db, document),
        user_id=document.uploaded_by,
        matter_id=document.matter_id,
        action="document_ingested",
        target_type="document",
        target_id=document.id,
        metadata={"page_count": len(parse_result.pages), "chunk_count": len(chunk_drafts)},
    )


def mark_ingest_failed(db: Session, document_id: UUID, exc: Exception) -> None:
    safe_error = exc.__class__.__name__
    document = db.get(Document, document_id)
    if document is not None:
        document.ingest_status = "failed"
        document.parse_status = "failed"
        document.error_message = safe_error
        organization_id = _organization_id_for_document(db, document)
    else:
        organization_id = None

    ingest_job = db.scalar(select(IngestJob).where(IngestJob.document_id == document_id))
    if ingest_job is not None:
        ingest_job.status = "failed"
        ingest_job.error_message = safe_error
        ingest_job.finished_at = utcnow()

    if document is not None and organization_id is not None:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=document.uploaded_by,
            matter_id=document.matter_id,
            action="ingest_job_failed",
            target_type="ingest_job",
            target_id=ingest_job.id if ingest_job else None,
            metadata={"document_id": str(document_id), "error_class": safe_error},
        )


def _start_ingest_job(db: Session, document: Document) -> IngestJob:
    ingest_job = db.scalar(
        select(IngestJob)
        .where(IngestJob.document_id == document.id)
        .order_by(IngestJob.created_at.desc())
        .limit(1)
    )
    if ingest_job is None:
        ingest_job = IngestJob(document_id=document.id, matter_id=document.matter_id)
        db.add(ingest_job)
        db.flush()

    ingest_job.status = "running"
    ingest_job.attempt_count = (ingest_job.attempt_count or 0) + 1
    ingest_job.started_at = ingest_job.started_at or utcnow()
    ingest_job.error_message = None
    document.ingest_status = "running"
    document.parse_status = "running"
    return ingest_job


def _organization_id_for_document(db: Session, document: Document) -> UUID:
    matter = db.get(Matter, document.matter_id)
    if matter is None:
        raise ValueError("Unable to resolve document matter")
    return matter.organization_id
