"""UI 测试用例模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class UiTestCase(Base):
    """UI 自动化测试用例."""

    __tablename__ = "ui_test_cases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(256), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(2048))  # 起始页面 URL
    browser_type: Mapped[str] = mapped_column(String(32), default="chrome")  # chrome/firefox/edge
    steps: Mapped[list] = mapped_column(JSONText, default=list)  # [{action, selector, value, description}]
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 失败重试配置（0=不重试）
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_interval: Mapped[float] = mapped_column(Float, default=2.0)  # 重试间隔（秒）
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
