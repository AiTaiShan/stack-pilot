from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from uuid import UUID


class ConfigCreate(BaseModel):
    key: str
    value: Any
    value_type: str
    description: Optional[str] = None
    is_sensitive: bool = False


class ConfigUpdate(BaseModel):
    value: Any
    value_type: str
    description: Optional[str] = None


class ConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    value: Any
    value_type: str
    description: Optional[str]
    is_sensitive: bool
