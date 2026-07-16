"""项目 Schema."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    """项目基础字段."""

    name: str = Field(..., max_length=128)
    description: str | None = None
    base_url: str | None = Field(default=None, max_length=512)
    code: str | None = Field(default=None, max_length=64)


class ProjectCreate(ProjectBase):
    """创建项目."""
    pass


class ProjectUpdate(BaseModel):
    """更新项目，全部字段可选."""
    name: str | None = None
    description: str | None = None
    base_url: str | None = None
    code: str | None = None


class ProjectResponse(ProjectBase):
    """项目响应."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


ProjectRole = Literal["viewer", "tester", "developer", "admin", "owner"]


class ProjectMemberCreate(BaseModel):
    user_id: str
    role: ProjectRole = "viewer"


class ProjectMemberUpdate(BaseModel):
    role: ProjectRole


class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    user_id: str
    role: ProjectRole
    created_by: str | None = None
    created_at: datetime | None = None
