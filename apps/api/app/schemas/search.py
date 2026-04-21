from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    document_ids: list[UUID] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    file_types: list[str] = Field(default_factory=list)
    document_types: list[str] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 10


class SearchResult(BaseModel):
    chunk_id: UUID | None = None
    document_id: UUID
    document_name: str
    page_number: int | None = None
    snippet: str
    score: float
    metadata: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]
