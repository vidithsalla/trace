"""Synchronous ingest of a plain-text source. Used by seeds, evals and tests.

Same path the worker takes for a .txt upload: store bytes, create an immutable version,
publish a versioned extraction, and mirror page/chunk rows for the V1 workflows.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.domain import Document, DocumentChunk, DocumentPage, Matter, User
from app.services.evidence_versions import (
    PageText,
    create_document_version,
    parser_profile,
    publish_extraction,
)
from app.services.parsers import normalize_text
from app.services.storage import storage_service


def ingest_text_document(db: Session, matter: Matter, user: User, name: str, text: str,
                         document: Document | None = None, change_note: str | None = None) -> Document:
    raw = text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    key = f"matters/{matter.id}/documents/{uuid4().hex}.txt"
    storage_service.upload_fileobj(key, BytesIO(raw), "text/plain")
    if document is None:
        document = Document(matter_id=matter.id, uploaded_by=user.id, file_name=name, display_name=name,
                            mime_type="text/plain", file_size_bytes=len(raw), storage_key=key,
                            sha256=digest, page_count=1, ingest_status="completed",
                            parse_status="completed", ocr_status="not_needed")
        db.add(document)
        db.flush()
    else:
        document.storage_key, document.sha256, document.file_size_bytes = key, digest, len(raw)
    version = create_document_version(db, document, storage_key=key, source_sha256=digest,
                                      file_name=name, mime_type="text/plain",
                                      file_size_bytes=len(raw), created_by=user.id,
                                      change_note=change_note)
    normalized = normalize_text(text)
    publish_extraction(db, version, [PageText(1, normalized)], profile=parser_profile("TextParser"))
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    db.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))
    db.add(DocumentPage(document_id=document.id, page_number=1, raw_text=text,
                        normalized_text=normalized, has_text_layer=True))
    db.add(DocumentChunk(document_id=document.id, matter_id=matter.id, page_start=1, page_end=1,
                         chunk_index=0, text=normalized, token_count=len(normalized.split())))
    db.flush()
    return document
