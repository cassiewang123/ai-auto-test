"""缺陷模式模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class DefectPattern(Base):
    """从失败执行记录中提取的缺陷模式."""

    __tablename__ = "defect_patterns"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(256), index=True)
    description: Mapped[str] = mapped_column(Text)
    pattern_type: Mapped[str] = mapped_column(String(32), index=True)
    # concurrency / null_pointer / boundary / auth / data_integrity / timeout / unknown
    related_interface: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    related_case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    # critical / high / medium / low
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(32), default="ai_analysis")
    # ai_analysis / manual
    ai_analysis_snapshot: Mapped[dict | None] = mapped_column(JSONText, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
