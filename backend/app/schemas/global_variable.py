"""全局变量管理的请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GlobalVariableBase(BaseModel):
    """全局变量基础字段."""

    name: str = Field(..., max_length=128, description="变量名")
    value: str = Field(default="", description="变量值（字符串形式存储）")
    var_type: str = Field(default="string", description="变量类型：string/number/boolean/json")
    description: str | None = Field(default=None, description="描述")
    scope: str = Field(default="global", description="作用域：global/workspace")
    project_id: str | None = Field(default=None, description="工作空间作用域时绑定的项目 ID")


class GlobalVariableCreate(GlobalVariableBase):
    """创建全局变量."""

    pass


class GlobalVariableUpdate(BaseModel):
    """更新全局变量，全部字段可选."""

    name: str | None = Field(default=None, max_length=128)
    value: str | None = None
    var_type: str | None = None
    description: str | None = None
    scope: str | None = None
    project_id: str | None = None


class GlobalVariableResponse(GlobalVariableBase):
    """全局变量响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("value", mode="before")
    @classmethod
    def normalize_oracle_empty_string(cls, value):
        return "" if value is None else value
