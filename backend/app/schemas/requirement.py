"""功能测试需求的请求/响应模型."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RequirementBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    source: str = "manual"
    priority: str = "P1"
    status: str = "draft"
    acceptance_criteria: str | None = None
    case_ids: list[str] = Field(default_factory=list)
    project_id: str | None = None


class RequirementCreate(RequirementBase):
    pass


class RequirementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    source: str | None = None
    priority: str | None = None
    status: str | None = None
    acceptance_criteria: str | None = None
    case_ids: list[str] | None = None
    project_id: str | None = None


class RequirementResponse(RequirementBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    coverage: int = 0


class RequirementStats(BaseModel):
    total: int = 0
    draft: int = 0
    active: int = 0
    covered: int = 0
    archived: int = 0
    total_cases: int = 0
