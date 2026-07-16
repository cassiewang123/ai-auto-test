"""通知日志模型：记录每次通知发送的结果."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationLog(Base):
    """通知发送日志."""

    __tablename__ = "notification_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # 关联渠道（可选，渠道删除后保留日志）
    channel_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("notification_channels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 渠道名称快照（渠道可能被删除）
    channel_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 事件类型
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    # 发送状态：success / failed
    status: Mapped[str] = mapped_column(String(16), index=True)
    # 消息内容或错误信息
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
