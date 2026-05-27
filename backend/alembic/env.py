from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import Base
from app.core.config import settings

# 导入所有模型以注册到 Base.metadata
from app.models.user import User
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.deployment import Deployment
from app.models.config import SystemConfig

# Alembic Config object
config = context.config

# 从 settings 获取数据库 URL
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置 target_metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """在 'offline' 模式下运行迁移。

    这会配置上下文，只需要一个 URL，不需要创建引擎。
    通过跳过引擎创建，我们可以在这里甚至不需要 DBAPI。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在 'online' 模式下运行迁移。

    创建引擎并将连接与上下文关联。
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
