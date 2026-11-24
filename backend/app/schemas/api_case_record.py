"""接口用例库（用例管理）请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiCaseRecordBase(BaseModel):
    """接口用例基础字段."""

    title: str = Field(..., min_length=1, max_length=256)
    method: str = Field(default="GET", max_length=16)
    url: str = Field(..., min_length=1, max_length=2048)
    headers: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: Any = None
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    case_type: str = Field(default="normal", max_length=16)
    priority: str = Field(default="P1", max_length=8)
    status: str = Field(default="active", max_length=16)
    description: str | None = None
    interface_name: str | None = Field(default=None, max_length=256)
    group_path: str | None = Field(default=None, max_length=256)
    project_id: str | None = Field(default=None, max_length=36)


class ApiCaseRecordCreate(ApiCaseRecordBase):
    """手工创建接口用例."""


class ApiCaseRecordUpdate(BaseModel):
    """更新接口用例（全部可选）."""

    title: str | None = Field(default=None, min_length=1, max_length=256)
    method: str | None = None
    url: str | None = None
    headers: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    body: Any = None
    assertions: list[dict[str, Any]] | None = None
    case_type: str | None = None
    priority: str | None = None
    status: str | None = None
    description: str | None = None
    interface_name: str | None = None
    group_path: str | None = None
    project_id: str | None = None
    is_active: bool | None = None


class ApiCaseRecordResponse(ApiCaseRecordBase):
    """接口用例响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str = "ai"
    is_active: bool = True
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApiCaseRecordStats(BaseModel):
    """接口用例统计."""

    total: int = 0
    normal: int = 0
    exception: int = 0
    boundary: int = 0
    permission: int = 0
    p0: int = 0


class ApiCaseBulkImportRequest(BaseModel):
    """把生成结果批量写入接口用例库."""

    cases: list[dict[str, Any]]
    project_id: str | None = None
    interface_name: str | None = None
    group_path: str | None = None


class ApiCaseBulkImportResponse(BaseModel):
    """批量写入结果."""

    created_count: int = 0
    case_ids: list[str] = Field(default_factory=list)
