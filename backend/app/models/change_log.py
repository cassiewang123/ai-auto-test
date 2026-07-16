"""接口变更历史模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class InterfaceChangeLog(Base):
    """接口变更历史记录."""

    __tablename__ = "interface_change_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    test_case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(16))  # created / updated / deleted
    # 变更前的快照
    before: Mapped[dict | None] = mapped_column(JSONText, default=None)
    # 变更后的快照
    after: Mapped[dict | None] = mapped_column(JSONText, default=None)
    # 变更字段列表
    changed_fields: Mapped[list | None] = mapped_column(JSONText, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
