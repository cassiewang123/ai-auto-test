"""契约测试的请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractVersionBase(BaseModel):
    """契约版本基础字段."""

    name: str = Field(..., max_length=200, description="契约名称")
    openapi_spec: dict[str, Any] | None = Field(default=None, description="OpenAPI 规范")
    project_id: str | None = Field(default=None, max_length=36, description="项目 ID")


class ContractCreate(ContractVersionBase):
    """创建契约（同时创建首个版本）."""

    pass


class ContractVersionCreate(BaseModel):
    """新增契约版本."""

    name: str | None = Field(default=None, max_length=200, description="契约名称（留空则继承上一版本）")
    openapi_spec: dict[str, Any] | None = Field(default=None, description="OpenAPI 规范")


class ContractVersionResponse(BaseModel):
    """契约版本响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    name: str
    version: int
    openapi_spec: dict[str, Any] | None = None
    project_id: str | None = None
    status: str = "active"
    created_by: str | None = None
    created_at: datetime | None = None


class ContractValidateRequest(BaseModel):
    """校验接口是否符合契约."""

    method: str = Field(..., description="HTTP 方法，如 GET/POST")
    path: str = Field(..., description="接口路径，如 /api/v1/users")
    status_code: int | None = Field(default=None, description="实际响应状态码")
    request_body: dict[str, Any] | None = Field(default=None, description="实际请求体")
    response_body: dict[str, Any] | None = Field(default=None, description="实际响应体")
    response_headers: dict[str, Any] | None = Field(default=None, description="实际响应头")


class ContractDiffResponse(BaseModel):
    """契约版本差异响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    from_version: int
    to_version: int
    breaking_changes: list[dict[str, Any]] | None = None
    non_breaking_changes: list[dict[str, Any]] | None = None
    affected_test_cases: list[str] | None = None
    created_at: datetime | None = None
