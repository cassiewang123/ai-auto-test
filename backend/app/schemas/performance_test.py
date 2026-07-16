"""性能测试场景的请求/响应模型."""
from __future__ import annotations

from pydantic import BaseModel


class PerformanceTestCreate(BaseModel):
    """创建性能测试场景."""

    name: str
    description: str | None = None
    case_ids: list[str] = []
    config: dict = {}  # {users, spawn_rate, duration, ramp_up}
    project_id: str | None = None


class PerformanceTestUpdate(BaseModel):
    """更新性能测试场景（部分更新）."""

    name: str | None = None
    description: str | None = None
    case_ids: list[str] | None = None
    config: dict | None = None
    project_id: str | None = None
    status: str | None = None
