from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class ProjectCreate(BaseModel):
    name: str
    git_url: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_branch: Optional[str] = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    git_url: str
    owner_id: UUID
    description: Optional[str]
    default_branch: str
    is_archived: bool
    created_at: datetime

    class Config:
        from_attributes = True
