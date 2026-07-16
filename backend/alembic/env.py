"""Alembic 运行环境配置.

- 运行时从 app.config.get_settings() 读取 DATABASE_URL，覆盖 alembic.ini 中的配置
- 导入 app.models 包，确保所有 ORM 模型注册到 Base.metadata，供 autogenerate 检测
- 同时支持 offline（仅生成 SQL）与 online（直接操作数据库）两种迁移模式
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# 确保 backend 目录在 sys.path 中，以便能 import app.*
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 应用配置：从环境变量/.env 加载，覆盖 alembic.ini 中的 sqlalchemy.url
# 导入 models 包，确保所有模型被注册到 Base.metadata（autogenerate 必需）
import app.models  # noqa: E402, F401
from app.config import get_settings  # noqa: E402

# 数据库基类与引擎
from app.database import Base, engine  # noqa: E402
from app.database_types import JSONText  # noqa: E402

# Alembic 配置对象
config = context.config

# 用应用 settings 中的 DATABASE_URL 覆盖 alembic.ini 的配置
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 日志配置（如果 alembic.ini 中定义了）
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 比对的目标 metadata
target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """Render JSONText columns as portable Text/CLOB migration types."""
    if type_ == "type" and isinstance(obj, JSONText):
        return "sa.Text()"
    return False


def run_migrations_offline() -> None:
    """离线模式：仅根据 DATABASE_URL 生成 SQL 脚本，不连接数据库."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite 下比较类型/服务器默认值容易产生噪声，按需开启
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库并执行迁移.

    优先复用 app.database 中已创建的 engine（保持 check_same_thread 等参数一致）。
    """

    def process_sql_url(url: str) -> str:
        return url

    # 复用应用已有的 engine，确保 SQLite 等连接参数与运行时一致
    connectable = engine

    if connectable is None:
        # 兜底：从配置构建 engine
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        def include_object(object_, name, type_, reflected, compare_to):
            # SQLite implements INTEGER PRIMARY KEY autoincrement without
            # persisting SQL standard IDENTITY metadata. Ignore only this
            # portability difference during local migration checks.
            return not (
                connection.dialect.name == "sqlite"
                and type_ == "column"
                and name == "id"
                and getattr(getattr(object_, "table", None), "name", None)
                == "job_events"
            )

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite does not persist SQL standard IDENTITY metadata, so
            # comparing defaults there would report a permanent false drift.
            compare_server_default=connection.dialect.name != "sqlite",
            render_item=render_item,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
