from __future__ import annotations

import re
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Document, DocumentChunk, DocumentPage
from app.schemas.workflow import CitationPayload

SPACE_RE = re.compile(r"\s+")


def normalize_quote(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def build_viewer_url(matter_id: UUID, citation: CitationPayload) -> str:
    page = citation.page or 1
    params = [f"page={page}"]
    if citation.quote:
        params.append(f"quote={quote(citation.quote)}")
    if citation.chunk_id:
        params.append(f"chunk={citation.chunk_id}")
    return f"/matters/{matter_id}/documents/{citation.document_id}?{'&'.join(params)}"


def validate_citations(
    db: Session, matter_id: UUID, citations: list[CitationPayload]
) -> list[CitationPayload]:
    validated: list[CitationPayload] = []
    seen: set[tuple[UUID, UUID | None, int | None, str]] = set()

    for citation in citations:
        key = (
            citation.document_id,
            citation.chunk_id,
            citation.page,
            normalize_quote(citation.quote).lower(),
        )
        if key in seen:
            continue
        seen.add(key)

        document = db.get(Document, citation.document_id)
        if document is None or document.matter_id != matter_id:
            continue

        chunk = db.get(DocumentChunk, citation.chunk_id) if citation.chunk_id else None
        if citation.chunk_id and (
            chunk is None or chunk.document_id != document.id or chunk.matter_id != matter_id
        ):
            continue

        page = None
        if citation.page is not None:
            page = db.scalar(
                select(DocumentPage).where(
                    DocumentPage.document_id == document.id,
                    DocumentPage.page_number == citation.page,
                )
            )
            if page is None:
                continue

        quote_text = normalize_quote(citation.quote)
        source_texts = []
        if chunk is not None:
            source_texts.append(chunk.text)
        if page is not None and page.normalized_text:
            source_texts.append(page.normalized_text)
        if not any(_contains_quote(source_text, quote_text) for source_text in source_texts):
            continue

        validated.append(
            citation.model_copy(
                update={
                    "document_name": citation.document_name or document.display_name or document.file_name,
                    "viewer_url": build_viewer_url(matter_id, citation),
                    "validation_status": "validated",
                }
            )
        )

    return validated


def _contains_quote(source_text: str, quote_text: str) -> bool:
    source = normalize_quote(source_text).lower()
    quote_value = normalize_quote(quote_text).lower()
    return bool(quote_value) and quote_value in source
