import datetime as dt
from uuid import UUID

from pydantic import BaseModel, Field


class CitationPayload(BaseModel):
    id: UUID | None = None
    document_id: UUID
    document_name: str
    page: int | None = None
    chunk_id: UUID | None = None
    quote: str
    viewer_url: str | None = None
    validation_status: str | None = None


class GroundedQARequest(BaseModel):
    question: str
    evidence_only: bool = False
    limit: int = 6


class GroundedQAResponse(BaseModel):
    answer: str
    short_answer: str
    confidence: str
    citations: list[CitationPayload]
    open_questions: list[str] = Field(default_factory=list)
    unsupported_claims_detected: bool = False
    ai_run_id: UUID | None = None


class ChronologyRequest(BaseModel):
    topic: str | None = None
    entity_name: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    include_existing: bool = True
    limit: int = 20


class ChronologyEvent(BaseModel):
    id: UUID | None = None
    date: dt.date | None = None
    date_text: str | None = None
    date_confidence: str = "medium"
    title: str
    description: str
    entity_names: list[str] = Field(default_factory=list)
    citations: list[CitationPayload] = Field(default_factory=list)
    conflict_flag: bool = False
    confidence: str = "medium"
    source_type: str = "ai_extracted"


class ChronologyResponse(BaseModel):
    events: list[ChronologyEvent]
    unresolved_ambiguities: list[str] = Field(default_factory=list)
    ai_run_id: UUID | None = None


class ChronologyEventUpdate(BaseModel):
    date: dt.date | None = None
    date_text: str | None = None
    date_confidence: str | None = None
    title: str | None = None
    description: str | None = None
    entity_names: list[str] | None = None
    conflict_flag: bool | None = None
    confidence: str | None = None


class ContradictionRequest(BaseModel):
    topic: str
    limit: int = 16


class ContradictionItem(BaseModel):
    claim_a: str
    claim_b: str
    why_conflict: str
    severity: str
    citations_a: list[CitationPayload] = Field(default_factory=list)
    citations_b: list[CitationPayload] = Field(default_factory=list)
    side_a_label: str | None = None
    side_b_label: str | None = None
    confidence: str = "medium"


class ContradictionResponse(BaseModel):
    topic: str
    contradictions: list[ContradictionItem]
    ambiguities: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    ai_run_id: UUID | None = None


class MemoCreateRequest(BaseModel):
    issue: str
    limit: int = 12


class MemoUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    content_json: dict | None = None
    content_markdown: str | None = None


class MemoRead(BaseModel):
    id: UUID
    matter_id: UUID
    created_by: UUID
    title: str
    memo_type: str
    status: str
    source_run_id: UUID | None
    content_json: dict
    content_markdown: str | None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}
