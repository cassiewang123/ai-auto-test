"""数据驱动测试数据集的请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataSetCreate(BaseModel):
    """创建数据集."""

    name: str = Field(..., max_length=256)
    description: str | None = None
    format: str = Field(..., pattern=r"^(csv|json)$")
    data: str
    test_case_id: str


class DataSetUpdate(BaseModel):
    """更新数据集，全部字段可选."""

    name: str | None = Field(default=None, max_length=256)
    description: str | None = None
    format: str | None = Field(default=None, pattern=r"^(csv|json)$")
    data: str | None = None
    is_active: bool | None = None


class DataSetResponse(BaseModel):
    """数据集响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    format: str
    data: str
    variables: list[str] = Field(default_factory=list)
    test_case_id: str
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DataSetPreviewResponse(BaseModel):
    """数据集预览解析结果."""

    variables: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class DataDrivenExecutionRequest(BaseModel):
    """数据驱动执行请求."""

    test_case_id: str
    data_set_id: str | None = None
    environment_id: str | None = None


class DataDrivenExecutionResult(BaseModel):
    """数据驱动执行结果."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    results: list[dict[str, Any]] = Field(default_factory=list)
