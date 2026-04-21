from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID | None
    matter_id: UUID | None
    action: str
    target_type: str | None
    target_id: UUID | None
    metadata_json: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class AIRunRead(BaseModel):
    id: UUID
    matter_id: UUID
    user_id: UUID
    run_type: str
    model_name: str
    prompt_template_version: str
    status: str
    input_json: dict
    output_json: dict
    token_usage_json: dict
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
