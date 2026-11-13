"""Deterministic source-integrity gate (PRD section 8.4).

Answers only: does this cited passage exist, unchanged, in the stated version, inside this
matter and this run's pinned snapshot? It never says whether a claim is true.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import CorpusSnapshotMember, ExtractionPage, SourceSpan
from app.services.evidence_versions import sha256_text


@dataclass(frozen=True, slots=True)
class GateResult:
    state: str  # VERIFIED | INVALID | UNAVAILABLE
    reason: str | None = None


def check_span(db: Session, *, matter_id: UUID, snapshot_id: UUID, span_id: UUID,
               allowed_span_ids: frozenset[UUID] | None = None) -> GateResult:
    if allowed_span_ids is not None and span_id not in allowed_span_ids:
        return GateResult("INVALID", "UNKNOWN_EVIDENCE_REF")
    span = db.get(SourceSpan, span_id)
    if span is None:
        return GateResult("UNAVAILABLE", "SPAN_NOT_FOUND")
    if span.matter_id != matter_id:
        return GateResult("INVALID", "FOREIGN_MATTER")
    in_snapshot = db.scalar(select(CorpusSnapshotMember.extraction_version_id).where(
        CorpusSnapshotMember.snapshot_id == snapshot_id,
        CorpusSnapshotMember.matter_id == matter_id,
        CorpusSnapshotMember.extraction_version_id == span.extraction_version_id,
    ))
    if in_snapshot is None:
        return GateResult("INVALID", "NOT_IN_SNAPSHOT")
    page = db.get(ExtractionPage, (span.extraction_version_id, span.page_no))
    if page is None:
        return GateResult("UNAVAILABLE", "PAGE_TEXT_UNAVAILABLE")
    if not (0 <= span.normalized_start < span.normalized_end <= len(page.text)):
        return GateResult("INVALID", "OFFSET_MISMATCH")
    if page.text[span.normalized_start:span.normalized_end] != span.text:
        return GateResult("INVALID", "OFFSET_MISMATCH")
    if sha256_text(span.text) != span.quote_sha256:
        return GateResult("INVALID", "QUOTE_HASH_MISMATCH")
    return GateResult("VERIFIED")


def combine(results: list[GateResult]) -> tuple[str, list[str]]:
    """A claim's citations are VERIFIED only if every cited span is."""
    if not results:
        return "INVALID", ["NO_CITATIONS"]
    reasons = sorted({r.reason for r in results if r.reason})
    if any(r.state == "INVALID" for r in results):
        return "INVALID", reasons
    if any(r.state == "UNAVAILABLE" for r in results):
        return "UNAVAILABLE", reasons
    return "VERIFIED", []
