"""CI/CD 集成模块的请求/响应模型：API Token、Webhook、CI 触发."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# API Token
# ---------------------------------------------------------------------------

class ApiTokenCreate(BaseModel):
    """创建 API Token."""

    name: str = Field(..., max_length=128)
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    user_id: str | None = None


class ApiTokenResponse(BaseModel):
    """API Token 列表/详情响应（脱敏，不含明文 token）.

    SEC-03 改造：列表/详情仅返回 token_prefix（前 8 位），不返回完整 token。
    token_masked 保留用于向后兼容，值与 token_prefix 一致。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    token_prefix: str = ""
    token_masked: str = ""
    scopes: list[str] = []
    is_active: bool = True
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None


class ApiTokenCreateResponse(ApiTokenResponse):
    """创建 Token 时返回：额外携带一次性的明文 token."""

    token: str


# ---------------------------------------------------------------------------
# Webhook 配置
# ---------------------------------------------------------------------------

class WebhookConfigCreate(BaseModel):
    """创建 Webhook 配置."""

    name: str = Field(..., max_length=128)
    url: str = Field(..., max_length=2048)
    events: list[str] = Field(default_factory=list)
    secret: str | None = Field(
        default=None,
        max_length=256,
        description="Webhook HMAC secret; encrypted value must fit the 256-char column",
    )
    is_active: bool = True
    project_id: str | None = None


class WebhookConfigUpdate(BaseModel):
    """更新 Webhook 配置，全部字段可选."""

    name: str | None = None
    url: str | None = Field(
        default=None,
        description='Webhook URL；传回响应掩码 "****" 时保留原值',
    )
    events: list[str] | None = None
    secret: str | None = Field(default=None, max_length=256)
    is_active: bool | None = None
    project_id: str | None = None


class WebhookConfigResponse(BaseModel):
    """Webhook 配置响应（不含完整 URL 或明文 secret）."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    has_url: bool = False
    events: list[str] = []
    has_secret: bool = False
    is_active: bool = True
    project_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def mask_webhook_url(self) -> WebhookConfigResponse:
        self.has_url = bool(self.url)
        self.url = "****" if self.has_url else ""
        return self


# ---------------------------------------------------------------------------
# CI 触发
# ---------------------------------------------------------------------------

class CiTriggerRequest(BaseModel):
    """CI/CD 触发执行请求：plan_id 或 case_ids 二选一."""

    plan_id: str | None = None
    case_ids: list[str] = []
    environment_id: str | None = None

    @model_validator(mode="after")
    def _check_target(self) -> CiTriggerRequest:
        if not self.plan_id and not self.case_ids:
            raise ValueError("必须提供 plan_id 或 case_ids 之一")
        if self.plan_id and self.case_ids:
            raise ValueError("plan_id 与 case_ids 不能同时提供")
        return self


class CiTriggerResponse(BaseModel):
    """CI/CD 触发执行响应."""

    run_id: str
    status: str
    message: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0
