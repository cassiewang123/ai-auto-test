"""业务规则模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BusinessRule(Base):
    """测试业务规则."""

    __tablename__ = "business_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(256), index=True)
    rule_text: Mapped[str] = mapped_column(Text)
    rule_type: Mapped[str] = mapped_column(String(32), index=True)
    # test_point / boundary / exception / data_validation / security
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    module: Mapped[str | None] = mapped_column(String(128), nullable=True)
    related_defect_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("defect_patterns.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(32), default="manual")
    # manual / ai_extracted / defect_promoted
    priority: Mapped[str] = mapped_column(String(16), default="P1")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
