"""通知渠道模型：飞书/钉钉/企微/Slack Webhook."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base
from app.services.security.secret_crypto import encrypt_url

if TYPE_CHECKING:
    from app.models.notification_rule import NotificationRule


class NotificationChannel(Base):
    """通知渠道：一个 Webhook 机器人配置."""

    __tablename__ = "notification_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # 渠道名称
    name: Mapped[str] = mapped_column(String(128), index=True)
    # 渠道类型：feishu / dingtalk / wechat / slack
    type: Mapped[str] = mapped_column(String(32), index=True)
    # Webhook 地址：应用写入口以 enc:vN: 格式加密；历史明文由运行时兼容读取。
    webhook_url: Mapped[str] = mapped_column(Text)
    # 加签密钥（钉钉/飞书用，可选）
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 是否启用
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联的通知规则
    rules: Mapped[list[NotificationRule]] = relationship(  # noqa: F821
        back_populates="channel",
        cascade="all, delete-orphan",
    )

    @validates("webhook_url")
    def _encrypt_webhook_url(self, key: str, value: str) -> str:
        """Encrypt all ORM URL writes; loaded legacy plaintext remains readable."""
        encrypted = encrypt_url(value)
        return encrypted or ""
