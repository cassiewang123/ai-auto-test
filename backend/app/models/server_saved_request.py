"""Saved HTTP requests for the SSH server console tool."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class ServerSavedRequest(Base):
    """一条保存下来的接口请求，供服务器连接页重复执行."""

    __tablename__ = "server_saved_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128))
    method: Mapped[str] = mapped_column(String(16), default="GET")
    # Oracle 索引对长 UTF-8 字符串不友好，这里只做普通列
    url: Mapped[str] = mapped_column(String(4096))
    params: Mapped[dict | None] = mapped_column(JSONText, default=None)
    headers: Mapped[dict | None] = mapped_column(JSONText, default=None)
    body: Mapped[Any | None] = mapped_column(Text, default=None)
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
