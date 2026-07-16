"""质量门禁的请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QualityGateBase(BaseModel):
    """质量门禁基础字段."""

    name: str = Field(..., max_length=200, description="门禁名称")
    project_id: str | None = Field(default=None, max_length=36, description="项目 ID")
    rules: list[dict[str, Any]] | None = Field(default=None, description="门禁规则")
    mode: str = Field(default="block", max_length=20, description="门禁模式：block/warn/log")
    is_active: bool = Field(default=True, description="是否启用")


class QualityGateCreate(QualityGateBase):
    """创建质量门禁."""

    pass


class QualityGateUpdate(BaseModel):
    """更新质量门禁，全部字段可选."""

    name: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=36)
    rules: list[dict[str, Any]] | None = None
    mode: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class QualityGateResponse(BaseModel):
    """质量门禁响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    project_id: str | None = None
    rules: list[dict[str, Any]] | None = None
    mode: str = "block"
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QualityGateEvaluateRequest(BaseModel):
    """评估门禁请求."""

    run_id: str | None = Field(default=None, description="关联的执行记录 ID")
    project_id: str | None = Field(default=None, max_length=36, description="项目 ID")
    metrics: dict[str, Any] = Field(default_factory=dict, description="指标数据，如 pass_rate/coverage")


class QualityGateResultResponse(BaseModel):
    """质量门禁评估结果响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    gate_id: str
    project_id: str | None = None
    run_id: str | None = None
    passed: bool
    results: list[dict[str, Any]] | None = None
    triggered_by: str | None = None
    created_at: datetime | None = None
