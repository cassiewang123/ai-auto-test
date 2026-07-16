"""MockConfig 的创建/更新/响应 Schema（Phase 4 Mock 增强）."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FaultInjectionSpec(BaseModel):
    """故障注入配置（用于 Mock 响应）。"""

    delay_ms: int = Field(default=0, ge=0, description="额外响应延迟（毫秒）")
    timeout: bool = Field(default=False, description="模拟超时（不响应）")
    disconnect: bool = Field(default=False, description="立即断开连接")
    error_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="按概率返回错误状态码（0-1）"
    )
    error_status: int = Field(default=500, ge=100, le=599, description="错误状态码")
    rate_limit: int | None = Field(
        default=None, ge=1, description="速率限制：每秒最大请求数（暂未实现，预留字段）"
    )


class MockConfigBase(BaseModel):
    """MockConfig 基础字段。"""

    name: str = Field(..., max_length=128)
    method: str = Field(default="GET", max_length=16)
    path: str = Field(..., max_length=512)
    status_code: int = Field(default=200, ge=100, le=599)
    response_headers: dict[str, Any] = Field(default_factory=dict)
    response_body: str | None = None
    delay_ms: int = Field(default=0, ge=0)
    is_enabled: bool = True
    project_id: str | None = None


class MockConfigCreate(MockConfigBase):
    """创建 Mock 配置（含 Phase 4 增强字段）。"""

    response_template: str | None = Field(
        default=None, description="动态响应模板（支持 {{request.body.field}} 等变量）"
    )
    match_rules: dict[str, Any] | None = Field(
        default=None, description="请求字段匹配规则（JSON）"
    )
    priority: int = Field(default=0, ge=0, description="匹配优先级，数值越大越优先")
    stateful_config: dict[str, Any] | None = Field(
        default=None, description="状态化场景配置（JSON）"
    )
    fault_injection: FaultInjectionSpec | None = Field(
        default=None, description="故障注入配置"
    )


class MockConfigUpdate(BaseModel):
    """更新 Mock 配置（全部字段可选）。"""

    name: str | None = None
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    response_headers: dict[str, Any] | None = None
    response_body: str | None = None
    delay_ms: int | None = None
    is_enabled: bool | None = None
    project_id: str | None = None
    response_template: str | None = None
    match_rules: dict[str, Any] | None = None
    priority: int | None = None
    stateful_config: dict[str, Any] | None = None
    fault_injection: FaultInjectionSpec | None = None


class MockConfigResponse(MockConfigBase):
    """Mock 配置响应（含增强字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    response_template: str | None = None
    match_rules: dict[str, Any] | None = None
    priority: int = 0
    stateful_config: dict[str, Any] | None = None
    fault_injection: FaultInjectionSpec | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
