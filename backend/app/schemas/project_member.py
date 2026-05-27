from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class MemberAdd(BaseModel):
    username: str
    role: str = "developer"  # admin/developer/viewer


class MemberUpdate(BaseModel):
    role: str


class MemberResponse(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    username: str
    role: str
    invited_by: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True
