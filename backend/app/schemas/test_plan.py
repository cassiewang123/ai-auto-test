"""测试计划与计划项的请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.test_case import TestCaseResponse


class TestPlanItemCreate(BaseModel):
    """添加用例到计划."""

    test_case_id: str
    order: int = Field(default=0, ge=0)


class TestPlanItemResponse(BaseModel):
    """计划项响应（含关联用例）."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    plan_id: str
    test_case_id: str
    order: int
    test_case: TestCaseResponse | None = None


class TestPlanCreate(BaseModel):
    """创建测试计划."""

    name: str = Field(..., max_length=256)
    project_id: str = Field(..., max_length=36)
    description: str | None = Field(default=None, max_length=1024)
    environment_id: str | None = None
    execution_mode: str = Field(default="sequential", max_length=16)
    marker_filter: str | None = Field(default=None, max_length=64)
    stress_config: dict[str, Any] | None = None
    # 场景类型：single 独立执行 / chain 串联执行支持变量传递
    scenario_type: str = Field(default="single", max_length=16)
    # 失败策略：stop 遇失败中断 / continue 继续执行后续用例
    fail_strategy: str = Field(default="stop", max_length=16)


class TestPlanUpdate(BaseModel):
    """更新测试计划，全部字段可选."""

    name: str | None = None
    project_id: str | None = Field(default=None, max_length=36)
    description: str | None = None
    environment_id: str | None = None
    execution_mode: str | None = None
    marker_filter: str | None = None
    stress_config: dict[str, Any] | None = None
    is_active: bool | None = None
    scenario_type: str | None = None
    fail_strategy: str | None = None


class TestPlanResponse(BaseModel):
    """测试计划响应（含计划项列表）."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    project_id: str | None = None
    created_by: str | None = None
    description: str | None = None
    environment_id: str | None = None
    execution_mode: str
    marker_filter: str | None = None
    stress_config: dict[str, Any] | None = None
    scenario_type: str = "single"
    fail_strategy: str = "stop"
    is_active: bool = True
    items: list[TestPlanItemResponse] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
