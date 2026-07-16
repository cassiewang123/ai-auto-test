"""Mock 接口配置模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class MockConfig(Base):
    """Mock 接口配置."""

    __tablename__ = "mock_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128))
    method: Mapped[str] = mapped_column(String(16), default="GET")
    path: Mapped[str] = mapped_column(String(512), index=True)  # 如 /api/users
    # 响应状态码
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    # 响应头 JSON
    response_headers: Mapped[dict] = mapped_column(JSONText, default=dict)
    # 响应体（字符串）
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 响应延迟（毫秒）
    delay_ms: Mapped[int] = mapped_column(Integer, default=0)
    # 是否启用
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 关联项目
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # --- Phase 4 Mock 增强：故障注入 / 动态响应 / 匹配规则 ---
    # 动态响应模板（支持 {{request.body.field}} / {{request.headers.x-custom}} 变量替换）
    response_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON：请求字段匹配规则，如 {"headers.x-custom": "abc", "body.user_id": 123}
    match_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 匹配优先级，数值越大越优先匹配
    priority: Mapped[int] = mapped_column(Integer, default=0)
    # JSON：状态化场景配置（如基于会话状态返回不同响应）
    stateful_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON：故障注入配置
    # {
    #   "delay_ms": 0,
    #   "timeout": false,
    #   "disconnect": false,
    #   "error_rate": 0,
    #   "error_status": 500,
    #   "rate_limit": null
    # }
    fault_injection: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
