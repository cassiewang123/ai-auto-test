"""通知规则模型：事件与渠道的绑定."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.database_types import JSONText

if TYPE_CHECKING:
    from app.models.notification_channel import NotificationChannel


class NotificationRule(Base):
    """通知规则：指定事件触发时通过哪个渠道发送通知."""

    __tablename__ = "notification_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # 规则名称
    name: Mapped[str] = mapped_column(String(128))
    # 关联渠道
    channel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notification_channels.id", ondelete="CASCADE"),
        index=True,
    )
    # 事件类型：test_run.completed / test_run.failed /
    # scheduled_task.completed / perf_test.completed
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    # 关联项目（可选）
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 过滤条件，如 {"min_failure_rate": 0.1}
    filters: Mapped[dict | None] = mapped_column(JSONText, default=None)
    # 是否启用
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关联渠道
    channel: Mapped[NotificationChannel] = relationship(  # noqa: F821
        back_populates="rules"
    )
