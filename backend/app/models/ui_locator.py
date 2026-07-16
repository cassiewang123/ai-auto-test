"""UI 元素定位器版本管理模型（Phase 4 UI 增强）.

与 ``UiElement`` 不同，``UILocator`` 强调"定位器"本身的可演化：
- 支持多种 selector_type（css/role/text/test_id/xpath）
- alternative_selectors 保存备选定位器，主定位器失败时按顺序回退
- usage_count / last_used_at 用于热度统计与淘汰
- 配合 ``POST /ui-locators/{id}/suggest-fix`` 端点生成修复建议（不自动覆盖）
"""
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


class UILocator(Base):
    """UI 元素定位器（带版本与备选定位器）。"""

    __tablename__ = "ui_locators"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    page_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # css/role/text/test_id/xpath
    selector_type: Mapped[str] = mapped_column(String(30), default="css")
    selector_value: Mapped[str] = mapped_column(String(500), nullable=False)
    # JSON：备选定位器列表，如 [{"type":"css","value":".btn"},{"type":"text","value":"提交"}]
    alternative_selectors: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
