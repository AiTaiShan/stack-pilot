from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(JSONB, nullable=False)
    value_type = Column(String(20), nullable=False)
    description = Column(Text)
    default_value = Column(JSONB)
    validation_rule = Column(JSONB)
    is_sensitive = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
