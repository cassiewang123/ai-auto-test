"""功能测试用例的请求/响应模型."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FunctionalTestCaseBase(BaseModel):
    """功能测试用例基础字段."""

    title: str = Field(..., min_length=1, max_length=256)
    module: str | None = Field(default=None, max_length=128, description="所属模块")
    category: str = Field(default="功能", max_length=16, description="功能/异常/边界/权限/安全")
    priority: str = Field(default="P1", max_length=8, description="P0-P3")
    preconditions: str | None = Field(default=None, description="前置条件")
    steps: list[str] = Field(default_factory=list, description="操作步骤")
    expected: str | None = Field(default=None, description="预期结果")
    trace_source: str | None = Field(default=None, max_length=256, description="需求追溯")
    status: str = Field(default="active", max_length=16, description="draft/active/deprecated")
    requirement_id: str | None = Field(default=None, max_length=36)
    project_id: str | None = Field(default=None, max_length=36)


class FunctionalTestCaseCreate(FunctionalTestCaseBase):
    """手工创建功能测试用例."""


class FunctionalTestCaseUpdate(BaseModel):
    """更新功能测试用例（全部字段可选）."""

    title: str | None = Field(default=None, min_length=1, max_length=256)
    module: str | None = None
    category: str | None = None
    priority: str | None = None
    preconditions: str | None = None
    steps: list[str] | None = None
    expected: str | None = None
    trace_source: str | None = None
    status: str | None = None
    requirement_id: str | None = None
    project_id: str | None = None
    is_active: bool | None = None


class FunctionalTestCaseResponse(FunctionalTestCaseBase):
    """功能测试用例响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str = "manual"
    design_session_id: str | None = None
    is_active: bool = True
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # 最近一次执行结果（无执行记录时为空）
    last_result: str | None = None
    last_executed_at: datetime | None = None


class FunctionalTestCaseStats(BaseModel):
    """功能测试用例统计."""

    total: int = 0
    draft: int = 0
    active: int = 0
    deprecated: int = 0
    p0: int = 0
    covered_requirements: int = 0


class ExecutionCreate(BaseModel):
    """登记一次人工执行记录."""

    result: str = Field(..., description="passed/failed/blocked/skipped")
    actual: str | None = Field(default=None, description="实际结果")
    remark: str | None = Field(default=None, description="备注")
    defect_ref: str | None = Field(default=None, max_length=128, description="缺陷单号")
    run_label: str | None = Field(default=None, max_length=64, description="执行轮次标签")


class ExecutionResponse(BaseModel):
    """执行记录响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    result: str
    actual: str | None = None
    remark: str | None = None
    defect_ref: str | None = None
    run_label: str | None = None
    executed_by: str | None = None
    executed_at: datetime | None = None
