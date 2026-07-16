"""UI 测试执行记录模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class UiTestRecord(Base):
    """UI 测试用例执行记录."""

    __tablename__ = "ui_test_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ui_test_cases.id", ondelete="CASCADE"), index=True
    )
    # 冗余存储用例标题（防止用例被删后记录丢失信息）
    case_title: Mapped[str] = mapped_column(String(256))
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048))  # 执行的 URL
    browser_type: Mapped[str] = mapped_column(String(32), default="chrome")
    status: Mapped[str] = mapped_column(String(16), index=True)  # passed/failed/error
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    passed_steps: Mapped[int] = mapped_column(Integer, default=0)
    failed_steps: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_results: Mapped[list | None] = mapped_column(JSONText, default=None)  # 详细步骤执行结果
    # 重试记录：每次尝试的 {attempt, status, duration, error}
    retry_attempts: Mapped[list] = mapped_column(JSONText, default=list)
    # 最终成功时的尝试次数（1=首次即成功）
    final_attempt: Mapped[int] = mapped_column(Integer, default=1)
    triggered_by: Mapped[str] = mapped_column(
        String(128), default="manual"
    )  # manual/scheduled
    executed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
