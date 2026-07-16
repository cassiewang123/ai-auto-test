"""测试用例与断言规则的请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 断言规则
# ---------------------------------------------------------------------------
class AssertionRuleBase(BaseModel):
    """断言规则基础字段."""

    assertion_type: str = Field(..., max_length=32, description="断言类型")
    expression: str | None = Field(default=None, description="JSONPath/Header名等")
    operator: str = Field(default="eq", max_length=16, description="比较操作符")
    expected: str | None = Field(default=None, description="期望值")
    priority: str = Field(default="P1", max_length=4, description="优先级 P0-P3")
    order: int = Field(default=0, ge=0, description="执行顺序")


class AssertionRuleCreate(AssertionRuleBase):
    """创建断言规则."""

    pass


class AssertionRuleResponse(AssertionRuleBase):
    """断言规则响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    test_case_id: str


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------
class TestCaseBase(BaseModel):
    """测试用例基础字段."""

    title: str = Field(..., max_length=256)
    method: str = Field(..., max_length=16)
    url: str = Field(..., max_length=2048)
    headers: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict | None = None
    markers: list[str] = Field(default_factory=list)
    group_path: str | None = Field(default=None, max_length=256)
    extract_rules: list[dict[str, Any]] = Field(default_factory=list)


class TestCaseCreate(TestCaseBase):
    """创建测试用例（含断言规则级联创建）."""

    description: str | None = None
    graphql_query: str | None = None
    files: list[dict[str, Any]] | None = None
    environment_id: str | None = None
    project_id: str | None = None
    retry_count: int = Field(default=0, ge=0)
    retry_interval: float = Field(default=1.0, ge=0)
    pre_script: str | None = None
    post_script: str | None = None
    assertions: list[AssertionRuleCreate] = Field(default_factory=list)


class TestCaseUpdate(BaseModel):
    """更新测试用例，全部字段可选（不含断言规则，断言单独管理）."""

    title: str | None = None
    method: str | None = None
    url: str | None = None
    headers: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    body: dict | None = None
    markers: list[str] | None = None
    group_path: str | None = None
    extract_rules: list[dict[str, Any]] | None = None
    description: str | None = None
    graphql_query: str | None = None
    files: list[dict[str, Any]] | None = None
    environment_id: str | None = None
    project_id: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    retry_count: int | None = Field(default=None, ge=0)
    retry_interval: float | None = Field(default=None, ge=0)
    pre_script: str | None = None
    post_script: str | None = None


class TestCaseResponse(TestCaseBase):
    """测试用例响应（含断言规则）."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    description: str | None = None
    graphql_query: str | None = None
    files: list[dict[str, Any]] | None = None
    environment_id: str | None = None
    project_id: str | None = None
    is_active: bool = True
    sort_order: int = 0
    retry_count: int = 0
    retry_interval: float = 1.0
    pre_script: str | None = None
    post_script: str | None = None
    assertions: list[AssertionRuleResponse] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
