from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DeploymentCreate(BaseModel):
    git_url: str
    branch: str = "main"
    platform: str
    config: Dict[str, Any] = {}


class DeploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    user_id: Optional[UUID] = None
    git_url: Optional[str] = None
    branch: Optional[str] = None
    platform: str
    status: str
    current_step: Optional[str] = None
    progress: int = 0
    image_tag: Optional[str] = None
    deploy_url: Optional[str] = None
    commit_hash: Optional[str] = None
    commit_message: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class DeploymentStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    current_step: Optional[str] = None
    progress: int = 0
    error_message: Optional[str] = None
    can_resume: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DeploymentLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: Optional[datetime] = None
    level: str
    message: str
    details: Optional[Dict[str, Any]] = None
    step: Optional[str] = None


class DeploymentLogResponse(BaseModel):
    logs: List[DeploymentLogEntry]
