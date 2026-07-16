"""任务产物模型：ExecutionJob 执行产生的文件型产物（日志、截图、报告等）."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobArtifact(Base):
    """任务产物：日志、截图、报告、trace 等文件."""

    __tablename__ = "job_artifacts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("execution_jobs.id", ondelete="CASCADE"), index=True
    )
    # 产物类型：log / screenshot / report / trace / video ...
    artifact_type: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
