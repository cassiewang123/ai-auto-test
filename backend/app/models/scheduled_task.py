"""定时任务模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class ScheduledTask(Base):
    """定时执行测试用例的任务."""

    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128))
    # 执行模式：interval（循环间隔）/ cron（定时表达式）
    mode: Mapped[str] = mapped_column(String(16), default="interval")
    # interval 模式：间隔秒数；cron 模式：cron 表达式
    schedule_config: Mapped[str] = mapped_column(String(256))  # 如 "300" (秒) 或 "0 2 * * *"
    # 要执行的用例 ID 列表 JSON
    case_ids: Mapped[list] = mapped_column(JSONText, default=list)
    # 关联项目
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 是否启用
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 上次执行时间
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 上次执行结果
    last_run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
