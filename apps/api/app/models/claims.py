"""V3 claim/review models. DDL (constraints, triggers) lives in migration 0003."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    corpus_snapshot_id: Mapped[uuid.UUID]
    requested_by: Mapped[uuid.UUID]
    question: Mapped[str] = mapped_column(Text)
    retrieval_profile: Mapped[str] = mapped_column(Text)
    retrieval_config_sha256: Mapped[str] = mapped_column(Text)
    model_config: Mapped[dict] = mapped_column(JSONB)
    model_config_sha256: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    code_commit: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_records: Mapped[list] = mapped_column(JSONB, default=list)
    coverage: Mapped[dict] = mapped_column(JSONB, default=dict)
    idempotency_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetrievalCandidate(Base):
    __tablename__ = "retrieval_candidates"

    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    evidence_ref: Mapped[str] = mapped_column(Text, primary_key=True)
    matter_id: Mapped[uuid.UUID]
    source_span_id: Mapped[uuid.UUID]
    retrieval_role: Mapped[str] = mapped_column(Text)
    retriever: Mapped[str] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    for_claim_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    run_id: Mapped[uuid.UUID]
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    review_state: Mapped[str] = mapped_column(Text, default="UNREVIEWED")
    basis_state: Mapped[str] = mapped_column(Text, default="CURRENT")
    coverage_state: Mapped[str] = mapped_column(Text, default="CURRENT")
    review_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ClaimRevision(Base):
    __tablename__ = "claim_revisions"

    claim_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    matter_id: Mapped[uuid.UUID]
    text: Mapped[str] = mapped_column(Text)
    evidence_set_sha256: Mapped[str] = mapped_column(Text)
    corpus_snapshot_id: Mapped[uuid.UUID]
    source_gate_state: Mapped[str] = mapped_column(Text)
    source_gate_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    relation_candidate: Mapped[str] = mapped_column(Text)
    coverage: Mapped[dict] = mapped_column(JSONB, default=dict)
    open_questions: Mapped[list] = mapped_column(JSONB, default=list)
    created_by_actor_type: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _ts()


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    claim_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    claim_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_span_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    matter_id: Mapped[uuid.UUID]
    evidence_ref: Mapped[str] = mapped_column(Text)
    cited_by_model: Mapped[bool] = mapped_column(Boolean)
    evidence_role: Mapped[str] = mapped_column(Text)
    quote_integrity: Mapped[str] = mapped_column(Text)
    integrity_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    relation_candidate: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_role: Mapped[str] = mapped_column(Text)


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    claim_id: Mapped[uuid.UUID]
    claim_revision: Mapped[int] = mapped_column(Integer)
    evidence_set_sha256: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID]
    action: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_seq: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(Text)
    request_sha256: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class CoverageAlert(Base):
    __tablename__ = "coverage_alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    claim_id: Mapped[uuid.UUID]
    claim_revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    triggering_document_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="OPEN")
    detector_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class PacketExport(Base):
    __tablename__ = "packet_exports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    requested_by: Mapped[uuid.UUID]
    inclusion_policy: Mapped[str] = mapped_column(Text)
    claim_count: Mapped[int] = mapped_column(Integer)
    manifest_sha256: Mapped[str] = mapped_column(Text)
    storage_prefix: Mapped[str] = mapped_column(Text)
    files: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _ts()
