"""测试执行结果模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class TestResult(Base):
    """单条用例的执行结果."""

    __tablename__ = "test_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # 关联计划执行批次 ID
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    test_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_cases.id"), index=True
    )
    test_plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("test_plans.id"), nullable=True
    )
    environment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("environments.id"), nullable=True
    )
    # 状态：passed / failed / skipped / error
    status: Mapped[str] = mapped_column(String(16), index=True)
    # 执行耗时（秒）
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    # 请求与响应快照（JSON）
    request_snapshot: Mapped[dict | None] = mapped_column(JSONText, default=None)
    response_snapshot: Mapped[dict | None] = mapped_column(JSONText, default=None)
    # 断言结果明细（JSON 数组）
    assertion_results: Mapped[list | None] = mapped_column(JSONText, default=None)
    # 错误信息
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AI 归因（JSON）：{"root_cause": "...", "confidence": 0.9}
    ai_analysis: Mapped[dict | None] = mapped_column(JSONText, default=None)
    # 产物路径
    trace_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
