from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.domain import Document, DocumentChunk
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services.embeddings import cosine_similarity, get_embedding_client


TOKEN_RE = re.compile(r"[a-z0-9]+")
RRF_K = 60


def perform_search(db: Session, matter_id: UUID, payload: SearchRequest) -> SearchResponse:
    query = payload.query.strip()
    if not query:
        return SearchResponse(query=payload.query, total=0, results=[])

    candidates = _candidate_chunks(db, matter_id, payload)
    candidate_by_id = {chunk.id: (chunk, document) for chunk, document in candidates}

    lexical_ids = _lexical_ranked_ids(db, matter_id, query)
    lexical_rank = [
        chunk_id for chunk_id in lexical_ids if chunk_id in candidate_by_id
    ][: max(payload.limit * 4, payload.limit)]
    vector_rank = _vector_rank(candidates, query)[: max(payload.limit * 4, payload.limit)]

    scores: dict[UUID, float] = {}
    rank_sources: dict[UUID, dict] = {}
    for rank, chunk_id in enumerate(lexical_rank, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        rank_sources.setdefault(chunk_id, {})["lexical_rank"] = rank
    for rank, chunk_id in enumerate(vector_rank, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        rank_sources.setdefault(chunk_id, {})["vector_rank"] = rank

    ranked_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)[: payload.limit]
    results = []
    for chunk_id in ranked_ids:
        chunk, document = candidate_by_id[chunk_id]
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.display_name or document.file_name,
                page_number=chunk.page_start,
                snippet=_snippet(chunk.text, query),
                score=round(scores[chunk_id], 6),
                metadata={
                    **(chunk.metadata_json or {}),
                    **rank_sources.get(chunk_id, {}),
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "mime_type": document.mime_type,
                },
            )
        )

    return SearchResponse(query=payload.query, total=len(results), results=results)


def _candidate_chunks(
    db: Session, matter_id: UUID, payload: SearchRequest
) -> list[tuple[DocumentChunk, Document]]:
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.matter_id == matter_id)
        .order_by(Document.created_at.desc(), DocumentChunk.chunk_index.asc())
    )
    if payload.document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(payload.document_ids))
    if payload.file_types:
        stmt = stmt.where(Document.mime_type.in_(payload.file_types))
    if payload.document_types:
        stmt = stmt.where(Document.document_type.in_(payload.document_types))
    if payload.date_from:
        stmt = stmt.where(Document.document_date >= payload.date_from)
    if payload.date_to:
        stmt = stmt.where(Document.document_date <= payload.date_to)

    rows = list(db.execute(stmt).all())
    if payload.entity_names:
        names = [name.lower() for name in payload.entity_names]
        rows = [
            (chunk, document)
            for chunk, document in rows
            if any(name in chunk.text.lower() for name in names)
        ]
    if payload.source_names:
        sources = [source.lower() for source in payload.source_names]
        rows = [
            (chunk, document)
            for chunk, document in rows
            if any(source in str(document.metadata_json or {}).lower() for source in sources)
        ]
    return rows


def _lexical_ranked_ids(db: Session, matter_id: UUID, query: str) -> list[UUID]:
    rows = db.execute(
        text(
            """
            SELECT id
            FROM document_chunks
            WHERE matter_id = :matter_id
              AND to_tsvector('english', text) @@ plainto_tsquery('english', :query)
            ORDER BY ts_rank_cd(
                to_tsvector('english', text),
                plainto_tsquery('english', :query)
            ) DESC,
            chunk_index ASC
            LIMIT 100
            """
        ),
        {"matter_id": matter_id, "query": query},
    ).all()
    return [row.id for row in rows]


def _vector_rank(candidates: list[tuple[DocumentChunk, Document]], query: str) -> list[UUID]:
    query_vector = get_embedding_client().embed_texts([query])[0]
    scored = [
        (chunk.id, cosine_similarity(chunk.embedding, query_vector))
        for chunk, _document in candidates
        if chunk.embedding is not None
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [chunk_id for chunk_id, score in scored if score > 0]


def _snippet(text_value: str, query: str) -> str:
    tokens = TOKEN_RE.findall(query.lower())
    lower_text = text_value.lower()
    first_match = min(
        [lower_text.find(token) for token in tokens if lower_text.find(token) >= 0] or [0]
    )
    start = max(first_match - 120, 0)
    end = min(start + 360, len(text_value))
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text_value) else ""
    return f"{prefix}{text_value[start:end].strip()}{suffix}"
