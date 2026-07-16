"""审计日志模型 (SEC-09).

记录用户对系统资源的操作行为，包括但不限于：
create / update / delete / execute / cancel / export / read_secret。
before / after 字段以 JSON 字符串存储，写入前经过 sanitize_dict 脱敏。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """审计日志：记录用户操作行为，用于安全审计与合规追踪。"""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # 操作人信息
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    # 操作类型：create / update / delete / execute / cancel / export / read_secret
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # 资源类型与 ID
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # 请求链路追踪
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 变更前后的快照（JSON 字符串，已脱敏）
    before: Mapped[str | None] = mapped_column(Text, nullable=True)
    after: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 执行结果
    result: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
