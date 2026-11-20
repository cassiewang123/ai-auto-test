"""功能测试需求模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class Requirement(Base):
    """一条功能测试需求，可关联多个测试用例."""

    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(256), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 需求来源：manual / import / jira / tapd
    source: Mapped[str] = mapped_column(String(32), default="manual")
    # 优先级：P0 / P1 / P2 / P3
    priority: Mapped[str] = mapped_column(String(8), default="P1")
    # 状态：draft / active / covered / archived
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    # 验收标准（文本）
    acceptance_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 关联的测试用例 ID 列表
    case_ids: Mapped[list] = mapped_column(JSONText, default=list)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
