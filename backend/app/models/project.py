"""项目模型：用于按项目分组管理接口测试用例."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    """测试项目：一个项目对应一个被测系统，包含多个接口用例."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 被测系统的基础 URL，如 http://robin.ep.local:30080
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 项目标识，用于快速识别
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 关联的测试用例
    test_cases: Mapped[list["TestCase"]] = relationship(  # noqa: F821
        back_populates="project", foreign_keys="TestCase.project_id"
    )
