"""API Token 模型：用于 CI/CD 与外部系统触发执行的认证凭证."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class ApiToken(Base):
    """API Token：通过 Authorization Bearer 或 X-API-Key 携带.

    scopes 示例：["test-cases:execute", "test-plans:execute"]
    token 存储时加 "air_" 前缀，使用 secrets.token_urlsafe(32) 生成。

    SEC-03 改造：明文 token 不再入库，仅存储 HMAC-SHA256 哈希值（token_hash）
    与前 8 位前缀（token_prefix，用于列表展示）。
    """

    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), index=True)
    # token 的 HMAC-SHA256 哈希值，唯一索引；明文 token 仅创建时返回一次
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    # token 前 8 位（如 "air_xxxx"），用于列表展示识别
    token_prefix: Mapped[str] = mapped_column(String(16), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scopes: Mapped[list] = mapped_column(JSONText, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
