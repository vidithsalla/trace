from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MatterBase(BaseModel):
    name: str
    description: str | None = None
    matter_code: str | None = None


class MatterCreate(MatterBase):
    pass


class MatterUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    matter_code: str | None = None
    status: str | None = None


class MatterListItem(MatterBase):
    id: UUID
    organization_id: UUID
    status: str
    created_by: UUID
    role: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MatterDetail(MatterListItem):
    archived_at: datetime | None = None
