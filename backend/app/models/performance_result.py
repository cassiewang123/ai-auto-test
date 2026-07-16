"""性能测试结果模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class PerformanceResult(Base):
    """性能测试执行结果."""

    __tablename__ = "performance_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    test_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("performance_tests.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    success_requests: Mapped[int] = mapped_column(Integer, default=0)
    fail_requests: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_time: Mapped[float] = mapped_column(Float, default=0.0)
    min_response_time: Mapped[float] = mapped_column(Float, default=0.0)
    max_response_time: Mapped[float] = mapped_column(Float, default=0.0)
    p50: Mapped[float] = mapped_column(Float, default=0.0)
    p90: Mapped[float] = mapped_column(Float, default=0.0)
    p95: Mapped[float] = mapped_column(Float, default=0.0)
    p99: Mapped[float] = mapped_column(Float, default=0.0)
    rps: Mapped[float] = mapped_column(Float, default=0.0)  # 每秒请求数
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[dict] = mapped_column(JSONText, default=dict)  # 每个用例的详细统计
    # SLA 评估结果（功能16）
    sla_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # passed/failed/warning
    sla_details: Mapped[dict] = mapped_column(JSONText, default=dict)  # SLA 各项评估详情
    # 压测模式（功能14），记录本次执行使用的模式
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
