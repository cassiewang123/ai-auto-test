"""统一任务中心数据模型：ExecutionJob / ExecutionAttempt / JobEvent.

ExecutionJob 表示一次测试执行任务（接口用例/UI 用例/UI 套件/性能测试），
ExecutionAttempt 记录每次尝试，JobEvent 以追加日志形式记录任务生命周期事件，
供前端通过轮询或 WebSocket 增量消费。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText

# 任务状态枚举
JOB_STATUSES = (
    "queued",       # 已入队，等待执行
    "running",      # 执行中
    "succeeded",    # 成功
    "failed",       # 失败
    "cancelled",    # 已取消
    "timed_out",    # 超时
)

# 可取消的中间状态
_CANCELLABLE_STATUSES = {"queued", "running"}

# 终态
_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out"}


class ExecutionJob(Base):
    """统一任务：一次测试执行的顶层实体."""

    __tablename__ = "execution_jobs"
    __table_args__ = (
        UniqueConstraint(
            "created_by",
            "idempotency_key",
            name="uq_execution_jobs_creator_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # 任务类型：api_case / ui_case / ui_suite / performance
    job_type: Mapped[str] = mapped_column(String(32), index=True)
    # 关联资源 ID（如 TestCase.id / UiTestCase.id）
    resource_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # 原始配置（JSON）
    config: Mapped[dict] = mapped_column(JSONText, default=dict)
    # 创建时的请求快照（JSON 字符串，供重试复用）
    request_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 幂等键：相同 key 的创建请求返回已有任务
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ExecutionAttempt(Base):
    """任务的单次执行尝试."""

    __tablename__ = "execution_attempts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("execution_jobs.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="running")
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class JobEvent(Base):
    """任务事件：以追加日志形式记录任务生命周期，支持增量查询与 WebSocket 推送."""

    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("execution_jobs.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    # 单调递增序列号（按 job 维度），客户端据此增量拉取
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
