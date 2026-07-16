"""环境管理的请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EnvironmentBase(BaseModel):
    """环境基础字段."""

    name: str = Field(..., max_length=64, description="环境名称")
    base_url: str = Field(..., max_length=512, description="基础 URL")
    variables: dict[str, Any] = Field(default_factory=dict, description="环境变量")
    description: str | None = Field(default=None, description="描述")
    db_config: dict[str, Any] | None = Field(default=None, description="数据库连接配置")
    cookies: list[dict[str, Any]] = Field(default_factory=list, description="会话 Cookie 列表")


class EnvironmentCreate(EnvironmentBase):
    """创建环境."""

    pass


class EnvironmentUpdate(BaseModel):
    """更新环境，全部字段可选."""

    name: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, max_length=512)
    variables: dict[str, Any] | None = None
    description: str | None = None
    db_config: dict[str, Any] | None = None
    cookies: list[dict[str, Any]] | None = None
    is_active: bool | None = None


class EnvironmentResponse(BaseModel):
    """环境响应，所有敏感字段均已脱敏.

    SEC-08 改造：db_config 中的 password 被替换为 "****" 并新增 has_password 标记；
    cookies 中每个 cookie 的 value 固定显示为 "****" 并新增 has_value 标记。
    脱敏由 API 端点调用 app.core.sanitizer 完成。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    base_url: str
    variables: dict[str, Any] = Field(default_factory=dict)
    db_config: dict[str, Any] | None = None
    cookies: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EnvironmentDetailResponse(EnvironmentResponse):
    """环境详情响应；与列表响应使用相同的不可逆脱敏视图."""

    pass
