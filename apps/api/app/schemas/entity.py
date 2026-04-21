from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EntityKeyDocument(BaseModel):
    document_id: UUID
    document_name: str
    mention_count: int


class EntityMentionRead(BaseModel):
    id: UUID
    entity_id: UUID
    document_id: UUID
    document_name: str
    chunk_id: UUID | None
    page_number: int | None
    mention_text: str
    context_text: str | None
    viewer_url: str | None
    confidence: float | None
    metadata_json: dict
    created_at: datetime


class EntityTimelineItem(BaseModel):
    event_id: UUID
    date: date | None
    date_text: str | None
    title: str
    description: str
    conflict_flag: bool


class EntityRead(BaseModel):
    id: UUID
    matter_id: UUID
    entity_type: str
    canonical_name: str
    aliases_json: list
    summary_json: dict
    confidence: float | None
    is_user_curated: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EntityListItem(EntityRead):
    mention_count: int = 0
    key_documents: list[EntityKeyDocument] = Field(default_factory=list)
    last_seen_at: datetime | None = None


class EntityDetailRead(EntityListItem):
    mentions: list[EntityMentionRead] = Field(default_factory=list)
    timeline: list[EntityTimelineItem] = Field(default_factory=list)


class EntityAliasCreate(BaseModel):
    alias: str


class EntityMergeRequest(BaseModel):
    source_entity_id: UUID
