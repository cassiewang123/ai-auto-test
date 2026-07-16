"""测试结果与报告汇总的响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TestResultResponse(BaseModel):
    """单条执行结果响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    test_case_id: str
    test_plan_id: str | None = None
    environment_id: str | None = None
    status: str
    duration: float = 0.0
    request_snapshot: dict[str, Any] | None = None
    response_snapshot: dict[str, Any] | None = None
    assertion_results: list[dict[str, Any]] | None = None
    error_message: str | None = None
    error_traceback: str | None = None
    ai_analysis: dict[str, Any] | None = None
    trace_path: str | None = None
    screenshot_path: str | None = None
    executed_at: datetime | None = None


class TestRunSummary(BaseModel):
    """单次执行批次（run_id）的汇总统计."""

    run_id: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_sum: float = 0.0


class TrendPoint(BaseModel):
    """历史趋势中的一个日期数据点."""

    date: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
