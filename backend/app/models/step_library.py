"""可复用步骤组模型（Page Object Model 模式）.

将常用操作序列封装为可复用步骤组，在 UI 测试用例中通过
action="step_group" 引用，避免重复编写相同步骤。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class StepLibrary(Base):
    """可复用步骤组：封装一组常用 UI 操作步骤，供用例引用."""

    __tablename__ = "step_library"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)  # 步骤组名称，如"登录操作"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    steps: Mapped[list] = mapped_column(JSONText, default=list)  # JSON 数组，与 UiTestCase.steps 格式相同
    tags: Mapped[list] = mapped_column(JSONText, default=list)  # 标签列表
    usage_count: Mapped[int] = mapped_column(Integer, default=0)  # 被引用次数
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
