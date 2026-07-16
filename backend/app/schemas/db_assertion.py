"""数据库断言规则的请求/响应模型."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DbAssertionBase(BaseModel):
    name: str = Field(..., max_length=128)
    sql_template: str
    expected_result: dict = Field(default_factory=dict)
    is_active: bool = True

class DbAssertionCreate(DbAssertionBase):
    test_case_id: str

class DbAssertionUpdate(BaseModel):
    name: str | None = None
    sql_template: str | None = None
    expected_result: dict | None = None
    is_active: bool | None = None

class DbAssertionResponse(DbAssertionBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    test_case_id: str
    created_at: datetime | None = None
