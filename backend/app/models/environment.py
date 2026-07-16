"""环境与变量模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.database_types import JSONText


class Environment(Base):
    """测试环境：dev / staging / prod，每环境独立配置."""

    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str] = mapped_column(String(512))
    # 变量以 JSON 存储：{"token": "xxx", "db_url": "..."}
    variables: Mapped[dict] = mapped_column(JSONText, default=dict)
    # 数据库连接配置：{"host": "...", "port": 3306, "user": "root", "password": "***", "database": "app_db", "db_type": "mysql"}
    db_config: Mapped[dict | None] = mapped_column(JSONText, default=None)
    # 会话 Cookie 列表：[{"name": "session", "value": "xxx", "domain": "api.example.com", "path": "/"}]
    cookies: Mapped[list] = mapped_column(JSONText, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    test_cases: Mapped[list["TestCase"]] = relationship(  # noqa: F821
        back_populates="environment"
    )
