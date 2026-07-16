"""Webhook 配置模型：测试执行事件的回调通知配置."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.database import Base
from app.database_types import JSONText
from app.services.security.secret_crypto import encrypt_url


class WebhookConfig(Base):
    """Webhook 配置：当指定事件发生时，向 url 发送带签名的 POST 回调.

    events 示例：["test_run.completed", "test_run.failed"]
    secret 用于计算 X-Airetest-Signature（HMAC-SHA256）签名头。
    """

    __tablename__ = "webhook_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), index=True)
    # 回调地址：应用写入口以 enc:vN: 格式加密；历史明文由运行时兼容读取。
    url: Mapped[str] = mapped_column(String(2048))
    events: Mapped[list] = mapped_column(JSONText, default=list)
    secret: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    @validates("url")
    def _encrypt_url(self, key: str, value: str) -> str:
        """Encrypt all ORM URL writes; loaded legacy plaintext remains readable."""
        encrypted = encrypt_url(value, max_ciphertext_length=2048)
        return encrypted or ""
