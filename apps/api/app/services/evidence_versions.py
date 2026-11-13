"""Immutable document versions, extraction versions, source spans and corpus snapshots.

Invariants (PRD section 7):
- A source span belongs to one extraction version. Offsets are zero-based, half-open
  ``[start, end)`` over NFC-normalized page text, counted in Unicode code points.
- ``publish_extraction`` runs inside the caller's transaction. Everything it writes becomes
  visible together on commit or not at all, so retrieval never sees a half-built extraction.
- Publishing is idempotent per (document_version, parser_profile): a duplicate job is a no-op.
- Older versions are RETIRED, never deleted or rewritten, so past decisions keep their basis.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.domain import Document, DocumentPage, utcnow
from app.models.evidence import (
    CorpusSnapshot,
    CorpusSnapshotMember,
    DocumentVersion,
    ExtractionPage,
    ExtractionVersion,
    SourceEmbedding,
    SourceSpan,
)
from app.services.embeddings import LocalHashEmbeddingClient, get_embedding_client
from app.services.storage import storage_service

NORMALIZATION_VERSION = "nfc-ws-v1"
SEGMENTER_VERSION = "sentence-v1"
OFFSET_ENCODING = "unicode_codepoints_nfc"
MIN_SPAN_CHARS = 25
MAX_SPAN_CHARS = 700

_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z0-9\"'(\[])")
_PARAGRAPH = re.compile(r"\n\s*\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def profile_sha256(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode("utf-8")).hexdigest()


def parser_profile(parser_name: str) -> dict:
    return {
        "parser": parser_name,
        "normalization": NORMALIZATION_VERSION,
        "segmenter": SEGMENTER_VERSION,
        "offset_encoding": OFFSET_ENCODING,
    }


# ---------------------------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------------------------
def segment_spans(text: str) -> list[tuple[int, int]]:
    """Split page text into citation spans. Returns ``[start, end)`` code-point offsets.

    Spans are sentences (merged when very short, split when very long) within paragraphs.
    Every returned span satisfies ``text[start:end] == text[start:end].strip()``.
    """
    spans: list[tuple[int, int]] = []
    for para_start, para_end in _ranges(text, _PARAGRAPH):
        pieces = list(_ranges(text, _SENTENCE_END, para_start, para_end))
        merged: list[tuple[int, int]] = []
        for start, end in pieces:
            if merged and (merged[-1][1] - merged[-1][0]) < MIN_SPAN_CHARS:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        if len(merged) > 1 and (merged[-1][1] - merged[-1][0]) < MIN_SPAN_CHARS:
            last = merged.pop()
            merged[-1] = (merged[-1][0], last[1])
        for start, end in merged:
            spans.extend(_split_long(text, start, end))
    return spans


def _ranges(text: str, separator: re.Pattern, start: int = 0, end: int | None = None):
    end = len(text) if end is None else end
    cursor = start
    for match in separator.finditer(text, start, end):
        yield from _trimmed(text, cursor, match.start())
        cursor = match.end()
    yield from _trimmed(text, cursor, end)


def _trimmed(text: str, start: int, end: int):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if end > start:
        yield (start, end)


def _split_long(text: str, start: int, end: int) -> Iterable[tuple[int, int]]:
    while end - start > MAX_SPAN_CHARS:
        cut = text.rfind(" ", start + MAX_SPAN_CHARS // 2, start + MAX_SPAN_CHARS)
        if cut <= start:
            cut = start + MAX_SPAN_CHARS
        yield from _trimmed(text, start, cut)
        start = cut
    yield from _trimmed(text, start, end)


# ---------------------------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------------------------
def next_revision_no(db: Session, document_id: UUID) -> int:
    current = db.scalar(
        select(func.max(DocumentVersion.revision_no)).where(DocumentVersion.document_id == document_id)
    )
    return (current or 0) + 1


def create_document_version(
    db: Session,
    document: Document,
    *,
    storage_key: str,
    source_sha256: str,
    file_name: str,
    mime_type: str,
    file_size_bytes: int,
    created_by: UUID | None,
    change_note: str | None = None,
) -> DocumentVersion:
    version = DocumentVersion(
        matter_id=document.matter_id,
        document_id=document.id,
        revision_no=next_revision_no(db, document.id),
        source_sha256=source_sha256,
        provenance="verified",
        storage_key=storage_key,
        file_name=file_name,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        state="STAGING",
        created_by=created_by,
        change_note=change_note,
    )
    db.add(version)
    db.flush()
    return version


def pending_version_for(db: Session, document: Document) -> DocumentVersion:
    """Return the version an ingest job should process, creating revision 1 for legacy rows."""
    latest = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.revision_no.desc())
        .limit(1)
    )
    if latest is not None:
        return latest
    return _legacy_version(db, document)


def _legacy_version(db: Session, document: Document) -> DocumentVersion:
    digest = None
    provenance = "unknown_legacy"
    if storage_service.object_exists(document.storage_key):
        digest = hashlib.sha256(storage_service.get_object_bytes(document.storage_key)).hexdigest()
        provenance = "verified"
    version = DocumentVersion(
        matter_id=document.matter_id,
        document_id=document.id,
        revision_no=1,
        source_sha256=digest,
        provenance=provenance,
        storage_key=document.storage_key,
        file_name=document.file_name,
        mime_type=document.mime_type,
        file_size_bytes=document.file_size_bytes,
        state="STAGING",
        created_by=document.uploaded_by,
        change_note="backfilled from pre-V3 document",
    )
    db.add(version)
    db.flush()
    return version


@dataclass(frozen=True, slots=True)
class PageText:
    page_no: int
    text: str


def publish_extraction(
    db: Session,
    version: DocumentVersion,
    pages: Sequence[PageText],
    *,
    profile: dict,
    warnings: list[str] | None = None,
) -> ExtractionVersion:
    """Build and publish an extraction for ``version``. Idempotent; atomic with the caller's tx."""
    # Serialize concurrent jobs for the same version.
    db.execute(
        select(DocumentVersion.id).where(DocumentVersion.id == version.id).with_for_update()
    )
    digest = profile_sha256(profile)
    existing = db.scalar(
        select(ExtractionVersion).where(
            ExtractionVersion.document_version_id == version.id,
            ExtractionVersion.parser_profile_sha256 == digest,
        )
    )
    if existing is not None and existing.state == "READY":
        return existing
    if existing is not None:  # leftover STAGING/FAILED row from an earlier attempt
        db.delete(existing)
        db.flush()

    normalized_pages = [PageText(p.page_no, p.text) for p in pages]
    full_digest = sha256_text("\f".join(p.text for p in normalized_pages))
    extraction = ExtractionVersion(
        matter_id=version.matter_id,
        document_version_id=version.id,
        parser_profile=json.dumps(profile, sort_keys=True),
        parser_profile_sha256=digest,
        normalization_version=NORMALIZATION_VERSION,
        normalized_text_sha256=full_digest,
        page_count=len(normalized_pages),
        warnings=list(warnings or []),
        state="STAGING",
    )
    db.add(extraction)
    db.flush()

    spans: list[SourceSpan] = []
    for page in normalized_pages:
        db.add(ExtractionPage(extraction_version_id=extraction.id, page_no=page.page_no,
                              matter_id=version.matter_id, text=page.text,
                              text_sha256=sha256_text(page.text)))
        for start, end in segment_spans(page.text):
            quote = page.text[start:end]
            spans.append(SourceSpan(
                matter_id=version.matter_id, extraction_version_id=extraction.id,
                document_id=version.document_id, page_no=page.page_no, span_index=len(spans),
                normalized_start=start, normalized_end=end, text=quote,
                quote_sha256=sha256_text(quote), offset_encoding=OFFSET_ENCODING,
            ))
    db.add_all(spans)
    db.flush()

    warnings_out = list(extraction.warnings)
    embedders = [LocalHashEmbeddingClient()]
    configured = get_embedding_client()
    if embedding_profile_id(configured) != "hash-v1":
        embedders.append(configured)
    for embedder in embedders:
        try:
            write_embeddings(db, spans, embedder)
        except Exception:  # noqa: BLE001 - semantic provider down must not block publication
            if embedding_profile_id(embedder) == "hash-v1":
                raise
            warnings_out.append("SEMANTIC_EMBEDDING_UNAVAILABLE")

    if not spans:
        warnings_out.append("NO_TEXT_EXTRACTED")
    extraction.warnings = warnings_out
    extraction.span_count = len(spans)
    extraction.state = "READY"
    extraction.published_at = utcnow()
    db.flush()
    _activate_version(db, version)
    from app.services.change_control import on_version_published  # avoid import cycle

    on_version_published(db, version, extraction.id)
    return extraction


def _activate_version(db: Session, version: DocumentVersion) -> None:
    db.execute(
        update(DocumentVersion)
        .where(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.id != version.id,
            DocumentVersion.state == "READY",
            DocumentVersion.revision_no < version.revision_no,
        )
        .values(state="RETIRED")
    )
    if version.state != "READY":
        version.state = "READY"
        version.published_at = utcnow()
    document = db.get(Document, version.document_id)
    if document is not None:
        current = db.get(DocumentVersion, document.current_version_id) if document.current_version_id else None
        if current is None or current.revision_no <= version.revision_no:
            document.current_version_id = version.id
    db.flush()


def write_embeddings(db: Session, spans: Sequence[SourceSpan], embedder) -> int:
    """Embed spans with one profile. Skips spans that already have that profile."""
    if not spans:
        return 0
    profile_id = embedding_profile_id(embedder)
    have = set(db.scalars(select(SourceEmbedding.source_span_id).where(
        SourceEmbedding.embedding_profile_id == profile_id,
        SourceEmbedding.source_span_id.in_([span.id for span in spans]),
    )))
    todo = [span for span in spans if span.id not in have]
    if not todo:
        return 0
    vectors = embedder.embed_texts(span.text for span in todo)
    db.add_all(
        SourceEmbedding(source_span_id=span.id, embedding_profile_id=profile_id,
                        matter_id=span.matter_id, embedding=vector)
        for span, vector in zip(todo, vectors, strict=True)
    )
    db.flush()
    return len(todo)


def embedding_profile_id(embedder) -> str:
    return getattr(embedder, "profile_id", None) or (
        "hash-v1"
    )


def backfill_legacy_document(db: Session, document: Document) -> ExtractionVersion | None:
    """Give a pre-V3 document a version + extraction from its stored page text."""
    if document.current_version_id is not None:
        return None
    pages = db.scalars(
        select(DocumentPage).where(DocumentPage.document_id == document.id).order_by(DocumentPage.page_number)
    ).all()
    if not pages:
        return None
    version = pending_version_for(db, document)
    return publish_extraction(
        db, version,
        [PageText(p.page_number, p.normalized_text or "") for p in pages],
        profile=parser_profile("legacy_document_pages"),
        warnings=["LEGACY_EXTRACTION_FROM_STORED_PAGES"],
    )


# ---------------------------------------------------------------------------------------------
# Corpus snapshots
# ---------------------------------------------------------------------------------------------
def current_extraction_ids(db: Session, matter_id: UUID) -> list[UUID]:
    """Latest READY extraction of each document's current READY version in the matter."""
    rows = db.execute(
        select(ExtractionVersion.id, ExtractionVersion.document_version_id, ExtractionVersion.published_at)
        .join(DocumentVersion, DocumentVersion.id == ExtractionVersion.document_version_id)
        .join(Document, Document.current_version_id == DocumentVersion.id)
        .where(
            Document.matter_id == matter_id,
            DocumentVersion.matter_id == matter_id,
            DocumentVersion.state == "READY",
            ExtractionVersion.state == "READY",
        )
        .order_by(ExtractionVersion.document_version_id, ExtractionVersion.published_at.desc())
    ).all()
    chosen: dict[UUID, UUID] = {}
    for extraction_id, version_id, _ in rows:
        chosen.setdefault(version_id, extraction_id)
    return sorted(chosen.values(), key=str)


def snapshot_manifest(db: Session, extraction_ids: Sequence[UUID]) -> list[dict]:
    if not extraction_ids:
        return []
    rows = db.execute(
        select(ExtractionVersion.id, ExtractionVersion.normalized_text_sha256,
               DocumentVersion.document_id, DocumentVersion.revision_no, DocumentVersion.source_sha256)
        .join(DocumentVersion, DocumentVersion.id == ExtractionVersion.document_version_id)
        .where(ExtractionVersion.id.in_(extraction_ids))
    ).all()
    return sorted(
        ({"extraction_version_id": str(r[0]), "normalized_text_sha256": r[1],
          "document_id": str(r[2]), "revision_no": r[3], "source_sha256": r[4]} for r in rows),
        key=lambda m: m["extraction_version_id"],
    )


def create_snapshot(db: Session, matter_id: UUID, created_by: UUID | None) -> CorpusSnapshot:
    """Pin the current corpus. Identical corpora share one snapshot (content-addressed)."""
    extraction_ids = current_extraction_ids(db, matter_id)
    manifest = snapshot_manifest(db, extraction_ids)
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()
    existing = db.scalar(
        select(CorpusSnapshot).where(CorpusSnapshot.matter_id == matter_id,
                                     CorpusSnapshot.manifest_sha256 == digest)
    )
    if existing is not None:
        return existing
    try:
        with db.begin_nested():
            snapshot = CorpusSnapshot(matter_id=matter_id, manifest_sha256=digest,
                                      member_count=len(extraction_ids), created_by=created_by)
            db.add(snapshot)
            db.flush()
            db.add_all(CorpusSnapshotMember(snapshot_id=snapshot.id, extraction_version_id=eid,
                                            matter_id=matter_id) for eid in extraction_ids)
            db.flush()
    except IntegrityError:  # a concurrent request created the same snapshot first
        return db.scalars(
            select(CorpusSnapshot).where(CorpusSnapshot.matter_id == matter_id,
                                         CorpusSnapshot.manifest_sha256 == digest)
        ).one()
    return snapshot
