"""接口分组的请求/响应模型."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiGroupBase(BaseModel):
    """分组基础字段."""

    name: str = Field(..., min_length=1, max_length=128, description="分组名称")
    parent_path: str | None = Field(
        default=None, max_length=512, description="上级分组路径，留空为顶级模块"
    )
    description: str | None = Field(default=None, description="分组说明")
    sort_order: int = Field(default=0, description="排序，越小越靠前")
    project_id: str | None = Field(default=None, max_length=36)


class ApiGroupCreate(ApiGroupBase):
    """新建分组."""


class ApiGroupUpdate(BaseModel):
    """编辑分组（改名会同步更新其下所有接口的 group_path）."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_path: str | None = None
    description: str | None = None
    sort_order: int | None = None


class ApiGroupResponse(BaseModel):
    """分组响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    path: str
    name: str
    parent_path: str | None = None
    description: str | None = None
    sort_order: int = 0
    project_id: str | None = None
    # 该分组（含子分组）下接口数量
    case_count: int = 0
    # 是否仅由接口 group_path 推导而来（未在 api_groups 表中显式登记）
    derived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApiGroupListResponse(BaseModel):
    """分组列表（含接口推导出的分组）."""

    groups: list[ApiGroupResponse] = Field(default_factory=list)
    total: int = 0


class ApiGroupDeleteResult(BaseModel):
    """删除分组结果."""

    deleted: bool = True
    # 被移动到父分组的接口数量
    moved_cases: int = 0
