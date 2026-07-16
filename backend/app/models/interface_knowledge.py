"""接口知识模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class InterfaceKnowledge(Base):
    """接口相关知识."""

    __tablename__ = "interface_knowledge"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    interface_path: Mapped[str] = mapped_column(String(2048), index=True)
    method: Mapped[str] = mapped_column(String(8))
    field_meanings: Mapped[dict | None] = mapped_column(JSONText, default=None)
    dependencies: Mapped[list | None] = mapped_column(JSONText, default=None)
    common_headers: Mapped[dict | None] = mapped_column(JSONText, default=None)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
