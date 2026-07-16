"""测试运行批次汇总模型."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class TestRunSummary(Base):
    """一次批量执行的汇总记录."""

    __tablename__ = "test_run_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    # 执行来源：batch_execute / scheduled / manual
    source: Mapped[str] = mapped_column(String(32), default="manual")
    # 关联项目（可选）
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
        index=True,
    )
    # 统计
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    # 总耗时
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    # 执行人/触发者
    triggered_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 关联的定时任务（可选）
    scheduled_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # 汇总信息 JSON
    summary: Mapped[dict | None] = mapped_column(JSONText, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
