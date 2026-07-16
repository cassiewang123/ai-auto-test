"""History record model for quick tests and saved-case executions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class CallHistory(Base):
    """A complete request/response execution history record."""

    __tablename__ = "call_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    method: Mapped[str] = mapped_column(String(16), index=True)
    # Oracle indexes on long UTF-8 URLs can exceed the B-tree key limit.
    url: Mapped[str] = mapped_column(String(2048))
    headers: Mapped[dict | None] = mapped_column(JSONText, default=None)
    params: Mapped[dict | None] = mapped_column(JSONText, default=None)
    body: Mapped[dict | None] = mapped_column(JSONText, default=None)
    status_code: Mapped[int | None] = mapped_column(default=None)
    response_headers: Mapped[dict | None] = mapped_column(JSONText, default=None)
    response_body: Mapped[Any | None] = mapped_column(JSONText, default=None)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    assertion_results: Mapped[list | None] = mapped_column(JSONText, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pre_request_results: Mapped[list | None] = mapped_column(JSONText, default=None)
    has_files: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String(32), default="quick_test")
    test_case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    executed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
