"""add generate_review and env_review to deploymentstep enum

Revision ID: a1b2c3d4e5f6
Revises: 93f01520d7ac
Create Date: 2026-05-29 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '93f01520d7ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE deploymentstep ADD VALUE IF NOT EXISTS 'generate_review'")
    op.execute("ALTER TYPE deploymentstep ADD VALUE IF NOT EXISTS 'env_review'")


def downgrade() -> None:
    # PostgreSQL 不支持从枚举中删除值，只能重建类型
    pass
