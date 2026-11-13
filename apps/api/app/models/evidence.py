"""V3 evidence-versioning models. DDL (constraints, triggers) lives in migration 0002."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BIGINT, Boolean, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    revision_no: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str] = mapped_column(Text, default="verified")
    storage_key: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    state: Mapped[str] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExtractionVersion(Base):
    __tablename__ = "extraction_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    document_version_id: Mapped[uuid.UUID]
    parser_profile: Mapped[str] = mapped_column(Text)
    parser_profile_sha256: Mapped[str] = mapped_column(Text)
    normalization_version: Mapped[str] = mapped_column(Text)
    normalized_text_sha256: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    span_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    state: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExtractionPage(Base):
    __tablename__ = "extraction_pages"

    extraction_version_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    page_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    matter_id: Mapped[uuid.UUID]
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(Text)


class SourceSpan(Base):
    __tablename__ = "source_spans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    extraction_version_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    page_no: Mapped[int] = mapped_column(Integer)
    span_index: Mapped[int] = mapped_column(Integer)
    normalized_start: Mapped[int] = mapped_column(Integer)
    normalized_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    quote_sha256: Mapped[str] = mapped_column(Text)
    offset_encoding: Mapped[str] = mapped_column(Text, default="unicode_codepoints_nfc")
    raw_anchor_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class EmbeddingProfile(Base):
    __tablename__ = "embedding_profiles"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    model_id: Mapped[str] = mapped_column(Text)
    dimension: Mapped[int] = mapped_column(Integer)
    normalization: Mapped[str] = mapped_column(Text)
    is_semantic: Mapped[bool] = mapped_column(Boolean)


class SourceEmbedding(Base):
    __tablename__ = "source_embeddings"

    source_span_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    embedding_profile_id: Mapped[str] = mapped_column(Text, primary_key=True)
    matter_id: Mapped[uuid.UUID]
    embedding: Mapped[list[float]] = mapped_column(Vector(384))


class CorpusSnapshot(Base):
    __tablename__ = "corpus_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID]
    manifest_sha256: Mapped[str] = mapped_column(Text)
    member_count: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CorpusSnapshotMember(Base):
    __tablename__ = "corpus_snapshot_members"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    extraction_version_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    matter_id: Mapped[uuid.UUID]
