from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ExportJobRead(BaseModel):
    id: UUID
    matter_id: UUID
    requested_by: UUID
    export_type: str
    status: str
    source_object_type: str
    source_object_id: UUID
    storage_key: str | None
    download_url: str | None = None
    error_message: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
