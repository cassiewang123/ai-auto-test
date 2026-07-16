"""通知管理的请求/响应模型."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# 渠道
# ---------------------------------------------------------------------------
class ChannelCreate(BaseModel):
    """创建通知渠道."""

    name: str = Field(..., max_length=128, description="渠道名称")
    type: str = Field(..., max_length=32, description="渠道类型：feishu/dingtalk/wechat/slack")
    webhook_url: str = Field(..., description="Webhook 地址")
    secret: str | None = Field(
        default=None,
        max_length=4096,
        description="加签密钥（钉钉/飞书用）",
    )
    is_active: bool = Field(default=True, description="是否启用")


class ChannelUpdate(BaseModel):
    """更新通知渠道，全部字段可选."""

    name: str | None = Field(default=None, max_length=128)
    type: str | None = Field(default=None, max_length=32)
    webhook_url: str | None = Field(
        default=None,
        description='Webhook 地址；传回响应掩码 "****" 时保留原值',
    )
    secret: str | None = Field(default=None, max_length=4096)
    is_active: bool | None = None


class ChannelResponse(BaseModel):
    """通知渠道响应（脱敏，不含完整 URL 或明文 secret）.

    URL 字段保留用于客户端兼容，但固定显示为 "****"，并由 has_url 标识
    是否已配置。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    webhook_url: str
    has_url: bool = False
    has_secret: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def mask_webhook_url(self) -> ChannelResponse:
        self.has_url = bool(self.webhook_url)
        self.webhook_url = "****" if self.has_url else ""
        return self


# ---------------------------------------------------------------------------
# 规则
# ---------------------------------------------------------------------------
class RuleCreate(BaseModel):
    """创建通知规则."""

    name: str = Field(..., max_length=128, description="规则名称")
    channel_id: str = Field(..., description="关联渠道 ID")
    event_type: str = Field(..., max_length=64, description="事件类型")
    project_id: str | None = Field(default=None, description="关联项目（可选）")
    filters: dict[str, Any] | None = Field(default=None, description="过滤条件")
    is_active: bool = Field(default=True, description="是否启用")


class RuleUpdate(BaseModel):
    """更新通知规则，全部字段可选."""

    name: str | None = Field(default=None, max_length=128)
    channel_id: str | None = None
    event_type: str | None = Field(default=None, max_length=64)
    project_id: str | None = None
    filters: dict[str, Any] | None = None
    is_active: bool | None = None


class RuleResponse(BaseModel):
    """通知规则响应（含渠道名称）."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    channel_id: str
    event_type: str
    project_id: str | None = None
    filters: dict[str, Any] | None = None
    is_active: bool = True
    created_at: datetime | None = None
    channel_name: str | None = None


# ---------------------------------------------------------------------------
# 测试通知
# ---------------------------------------------------------------------------
class TestNotificationRequest(BaseModel):
    """发送测试通知请求."""

    title: str | None = Field(default=None, description="自定义标题")
    content: str | None = Field(default=None, description="自定义内容")


# ---------------------------------------------------------------------------
# 通知日志
# ---------------------------------------------------------------------------
class NotificationLogResponse(BaseModel):
    """通知日志响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    channel_name: str | None = None
    project_id: str | None = None
    event_type: str
    status: str
    message: str | None = None
    created_at: datetime | None = None
