import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class DeploymentStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class DeploymentStep(str, enum.Enum):
    CLONE = "clone"
    BUILD = "build"
    PUSH = "push"
    DEPLOY = "deploy"
    CONFIGURE = "configure"
    VERIFY = "verify"


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(
        Enum(DeploymentStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DeploymentStatus.PENDING,
    )
    current_step = Column(
        Enum(DeploymentStep, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    progress = Column(Integer, nullable=False, default=0)
    platform = Column(String(20), nullable=False)
    config = Column(JSONB)
    git_url = Column(String(500))
    branch = Column(String(200), default="main")
    image_tag = Column(String(500))
    deploy_url = Column(String(500))
    commit_hash = Column(String(40))
    commit_message = Column(Text)
    error_message = Column(Text)
    error_details = Column(JSONB)
    can_resume = Column(Integer, default=0)
    resume_data = Column(JSONB)
    duration = Column(Integer)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    checkpoints = relationship("DeploymentCheckpoint", back_populates="deployment", cascade="all, delete-orphan")
    logs = relationship("DeploymentLog", back_populates="deployment", cascade="all, delete-orphan")


class DeploymentCheckpoint(Base):
    __tablename__ = "deployment_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id"), nullable=False)
    step = Column(String(50), nullable=False)
    step_index = Column(Integer, nullable=False)
    state_data = Column(JSONB)
    resources_created = Column(JSONB)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    deployment = relationship("Deployment", back_populates="checkpoints")


class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id"), nullable=False)
    level = Column(String(20), nullable=False, default="info")
    message = Column(Text, nullable=False)
    details = Column(JSONB)
    step = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    deployment = relationship("Deployment", back_populates="logs")
