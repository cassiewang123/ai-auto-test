"""接口用例库（用例管理）请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # 模块（分组）数量：题库中出现过的模块路径数量
    group_count: int = 0


class ApiCaseBulkImportRequest(BaseModel):
    """把生成结果批量写入接口用例库."""

    # 前端选中行索引失效时可能传入 null/字符串/数组等非字典项。
    # 这里统一丢弃非法项，避免整批导入因 422 失败，合法的用例照常入库。
    cases: list[dict[str, Any]]
    project_id: str | None = Field(default=None, max_length=36)
    # 接口名可能来自很长的接口标题，这里不设上限，写入时会截断到字段长度
    interface_name: str | None = None
    group_path: str | None = None

    @field_validator("cases", mode="before")
    @classmethod
    def _drop_invalid_cases(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [item for item in value if isinstance(item, dict)]


class ApiCaseBulkImportResponse(BaseModel):
    """批量写入结果."""

    created_count: int = 0
    case_ids: list[str] = Field(default_factory=list)


class ApiCaseBatchIdsRequest(BaseModel):
    """批量操作（移动/删除）选择的用例 ID 列表."""

    case_ids: list[str] = Field(default_factory=list)
    # 移动到指定模块（分组）；空或 null 表示移出模块
    group_path: str | None = None

    @field_validator("case_ids", mode="before")
    @classmethod
    def _require_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("case_ids 必须是数组")
        return [str(item) for item in value if item]


class ApiCaseGroupItem(BaseModel):
    """模块（分组）条目：路径 + 用例数."""

    path: str
    name: str
    parent_path: str | None = None
    # 直属该模块的用例数
    direct_count: int = 0
    # 含子模块的累计用例数
    total_count: int = 0
