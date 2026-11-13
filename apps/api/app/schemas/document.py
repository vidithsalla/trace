from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentListItem(BaseModel):
    id: UUID
    matter_id: UUID
    file_name: str
    display_name: str | None
    mime_type: str
    file_size_bytes: int
    page_count: int | None
    document_type: str | None
    parse_status: str
    ocr_status: str
    ingest_status: str
    extraction_quality_score: float | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetail(DocumentListItem):
    uploaded_by: UUID
    storage_key: str
    sha256: str
    document_date: date | None
    language: str | None
    metadata_json: dict
    updated_at: datetime


class DocumentPageRead(BaseModel):
    id: UUID
    document_id: UUID
    page_number: int
    raw_text: str | None
    normalized_text: str | None
    image_storage_key: str | None
    ocr_confidence: float | None
    has_text_layer: bool
    metadata_json: dict

    model_config = {"from_attributes": True}
