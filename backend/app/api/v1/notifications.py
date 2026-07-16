"""通知管理 API：渠道/规则/日志 CRUD + 测试通知.

SEC-08 改造：渠道响应不含明文 secret，以 has_secret 布尔标记替代。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.database import get_db
from app.models.notification_channel import NotificationChannel
from app.models.notification_log import NotificationLog
from app.models.notification_rule import NotificationRule
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.schemas.notification import (
    ChannelCreate,
    ChannelResponse,
    ChannelUpdate,
    NotificationLogResponse,
    RuleCreate,
    RuleResponse,
    RuleUpdate,
    TestNotificationRequest,
)
from app.services.auth_service import get_current_user, require_superuser
from app.services.project_access import (
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)
from app.services.security.secret_crypto import (
    SecretCryptoError,
    encrypt_secret,
    mask_url,
    prepare_url_for_storage,
    redact_url_from_text,
)

router = APIRouter()

_VALID_TYPES = {"feishu", "dingtalk", "wechat", "slack"}


def _ensure_project_or_workspace_role(
    db: Session,
    user: User,
    project_id: str | None,
    minimum_role: str,
) -> None:
    """Authorize project resources; unscoped resources are workspace-admin only."""
    if user.is_superuser:
        return
    if not project_id:
        raise ForbiddenError("Workspace notification access requires superuser")
    ensure_project_role(db, user, project_id, minimum_role)


def _to_channel_response(ch: NotificationChannel) -> ChannelResponse:
    """将渠道转为不包含完整 URL 或明文 secret 的响应字典."""
    return ChannelResponse(
        id=ch.id,
        name=ch.name,
        type=ch.type,
        webhook_url=mask_url(ch.webhook_url),
        has_url=bool(ch.webhook_url),
        has_secret=bool(ch.secret),
        is_active=ch.is_active,
        created_at=ch.created_at,
        updated_at=ch.updated_at,
    )


# ===========================================================================
# 渠道
# ===========================================================================
@router.get("/channels", response_model=PageResponse[ChannelResponse])
def list_channels(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: str | None = Query(None, description="按名称模糊搜索"),
    type: str | None = Query(None, description="按类型筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """渠道列表分页（脱敏，不返回明文 secret）."""
    query = select(NotificationChannel)
    count_query = select(func.count()).select_from(NotificationChannel)
    if name:
        query = query.where(NotificationChannel.name.ilike(f"%{name}%"))
        count_query = count_query.where(NotificationChannel.name.ilike(f"%{name}%"))
    if type:
        query = query.where(NotificationChannel.type == type)
        count_query = count_query.where(NotificationChannel.type == type)

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(NotificationChannel.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[ChannelResponse](
        data=[_to_channel_response(ch) for ch in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/channels", response_model=DataResponse[ChannelResponse])
def create_channel(
    payload: ChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """创建渠道."""
    if payload.type not in _VALID_TYPES:
        raise ValidationError(
            f"渠道类型无效，仅支持: {', '.join(sorted(_VALID_TYPES))}",
            detail=f"type={payload.type}",
        )
    data = payload.model_dump()
    try:
        data["webhook_url"] = prepare_url_for_storage(data["webhook_url"])
        data["secret"] = encrypt_secret(data.get("secret"))
    except (SecretCryptoError, TypeError) as exc:
        raise ValidationError("通知敏感配置加密失败", detail=str(exc)) from exc
    channel = NotificationChannel(**data)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return DataResponse[ChannelResponse](data=_to_channel_response(channel))


@router.put("/channels/{channel_id}", response_model=DataResponse[ChannelResponse])
def update_channel(
    channel_id: str,
    payload: ChannelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """更新渠道（部分更新）."""
    channel = db.get(NotificationChannel, channel_id)
    if not channel:
        raise NotFoundError("通知渠道", channel_id)
    update_data = payload.model_dump(exclude_unset=True)
    if "type" in update_data and update_data["type"] is not None and update_data["type"] not in _VALID_TYPES:
        raise ValidationError(
            f"渠道类型无效，仅支持: {', '.join(sorted(_VALID_TYPES))}",
            detail=f"type={update_data['type']}",
        )
    if "secret" in update_data:
        try:
            update_data["secret"] = encrypt_secret(update_data["secret"])
        except (SecretCryptoError, TypeError) as exc:
            raise ValidationError("通知密钥加密失败", detail=str(exc)) from exc
    if "webhook_url" in update_data:
        if update_data["webhook_url"] is None:
            raise ValidationError("Webhook 地址不能为空")
        try:
            update_data["webhook_url"] = prepare_url_for_storage(
                update_data["webhook_url"],
                existing=channel.webhook_url,
            )
        except (SecretCryptoError, TypeError) as exc:
            raise ValidationError("Webhook 地址加密失败", detail=str(exc)) from exc
    for field, value in update_data.items():
        setattr(channel, field, value)
    db.commit()
    db.refresh(channel)
    return DataResponse[ChannelResponse](data=_to_channel_response(channel))


@router.delete("/channels/{channel_id}", response_model=DataResponse[ChannelResponse])
def delete_channel(
    channel_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """删除渠道（关联规则级联删除）."""
    channel = db.get(NotificationChannel, channel_id)
    if not channel:
        raise NotFoundError("通知渠道", channel_id)
    data = _to_channel_response(channel)
    db.delete(channel)
    db.commit()
    return DataResponse[ChannelResponse](data=data)


@router.post("/channels/{channel_id}/test", response_model=DataResponse[dict])
async def test_channel(
    channel_id: str,
    payload: TestNotificationRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """发送测试通知，返回发送结果并记录日志."""
    channel = db.get(NotificationChannel, channel_id)
    if not channel:
        raise NotFoundError("通知渠道", channel_id)

    content = payload.content if payload and payload.content else "这是一条测试通知消息，收到说明配置正确。"
    title = payload.title if payload and payload.title else "测试通知"
    event_type = "test"

    # 直接调用统一发送入口（使用自定义内容）
    from app.services.notification_service import (
        send_dingtalk,
        send_feishu,
        send_slack,
        send_wechat,
    )

    try:
        if channel.type == "feishu":
            await send_feishu(channel.webhook_url, channel.secret, title, content)
        elif channel.type == "dingtalk":
            await send_dingtalk(channel.webhook_url, channel.secret, title, content)
        elif channel.type == "wechat":
            await send_wechat(channel.webhook_url, title, content)
        elif channel.type == "slack":
            await send_slack(channel.webhook_url, title, content)
        else:
            raise ValueError(f"不支持的渠道类型: {channel.type}")
        status = "success"
        message = content
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        message = redact_url_from_text(
            str(exc),
            channel.webhook_url,
        )

    # 记录日志
    log = NotificationLog(
        channel_id=channel.id,
        project_id=None,
        channel_name=channel.name,
        event_type=event_type,
        status=status,
        message=message,
    )
    db.add(log)
    db.commit()

    return DataResponse(
        data={
            "success": status == "success",
            "status": status,
            "message": message,
        }
    )


# ===========================================================================
# 规则
# ===========================================================================
def _rule_to_response(rule: NotificationRule, db: Session) -> dict:
    """构造规则响应字典（含渠道名称）."""
    channel = db.get(NotificationChannel, rule.channel_id)
    return {
        "id": rule.id,
        "name": rule.name,
        "channel_id": rule.channel_id,
        "event_type": rule.event_type,
        "project_id": rule.project_id,
        "filters": rule.filters,
        "is_active": rule.is_active,
        "created_at": rule.created_at,
        "channel_name": channel.name if channel else None,
    }


@router.get("/rules", response_model=PageResponse[RuleResponse])
def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel_id: str | None = Query(None, description="按渠道筛选"),
    event_type: str | None = Query(None, description="按事件类型筛选"),
    project_id: str | None = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """规则列表分页."""
    query = select(NotificationRule)
    count_query = select(func.count()).select_from(NotificationRule)
    if project_id is not None:
        _ensure_project_or_workspace_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query,
        NotificationRule,
        current_user,
        owner_field=None,
    )
    count_query = scope_project_resources(
        count_query,
        NotificationRule,
        current_user,
        owner_field=None,
    )
    if channel_id:
        query = query.where(NotificationRule.channel_id == channel_id)
        count_query = count_query.where(NotificationRule.channel_id == channel_id)
    if event_type:
        query = query.where(NotificationRule.event_type == event_type)
        count_query = count_query.where(NotificationRule.event_type == event_type)
    if project_id is not None:
        query = query.where(NotificationRule.project_id == project_id)
        count_query = count_query.where(NotificationRule.project_id == project_id)

    total = db.execute(count_query).scalar_one()
    rules = (
        db.execute(query.order_by(NotificationRule.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    data = [_rule_to_response(r, db) for r in rules]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("/rules", response_model=DataResponse[RuleResponse])
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建规则."""
    _ensure_project_or_workspace_role(db, current_user, payload.project_id, "developer")
    channel = db.get(NotificationChannel, payload.channel_id)
    if not channel:
        raise NotFoundError("通知渠道", payload.channel_id)
    rule = NotificationRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return DataResponse(data=_rule_to_response(rule, db))


@router.put("/rules/{rule_id}", response_model=DataResponse[RuleResponse])
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新规则（部分更新）."""
    rule = db.get(NotificationRule, rule_id)
    if not rule:
        raise NotFoundError("通知规则", rule_id)
    ensure_resource_role(
        db,
        current_user,
        rule,
        "developer",
        owner_field=None,
    )
    update_data = payload.model_dump(exclude_unset=True)
    if "project_id" in update_data and update_data["project_id"] != rule.project_id:
        ensure_resource_role(
            db,
            current_user,
            rule,
            "admin",
            owner_field=None,
        )
        _ensure_project_or_workspace_role(
            db,
            current_user,
            update_data["project_id"],
            "admin",
        )
    if "channel_id" in update_data and update_data["channel_id"] is not None:
        channel = db.get(NotificationChannel, update_data["channel_id"])
        if not channel:
            raise NotFoundError("通知渠道", update_data["channel_id"])
    for field, value in update_data.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return DataResponse(data=_rule_to_response(rule, db))


@router.delete("/rules/{rule_id}", response_model=DataResponse[RuleResponse])
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除规则."""
    rule = db.get(NotificationRule, rule_id)
    if not rule:
        raise NotFoundError("通知规则", rule_id)
    ensure_resource_role(
        db,
        current_user,
        rule,
        "admin",
        owner_field=None,
    )
    data = _rule_to_response(rule, db)
    db.delete(rule)
    db.commit()
    return DataResponse(data=data)


# ===========================================================================
# 日志
# ===========================================================================
@router.get("/logs", response_model=PageResponse[NotificationLogResponse])
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel_id: str | None = Query(None, description="按渠道筛选"),
    event_type: str | None = Query(None, description="按事件类型筛选"),
    status: str | None = Query(None, description="按状态筛选：success/failed"),
    project_id: str | None = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """通知日志分页查询."""
    query = select(NotificationLog)
    count_query = select(func.count()).select_from(NotificationLog)
    if project_id is not None:
        _ensure_project_or_workspace_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query,
        NotificationLog,
        current_user,
        owner_field=None,
    )
    count_query = scope_project_resources(
        count_query,
        NotificationLog,
        current_user,
        owner_field=None,
    )
    if channel_id:
        query = query.where(NotificationLog.channel_id == channel_id)
        count_query = count_query.where(NotificationLog.channel_id == channel_id)
    if event_type:
        query = query.where(NotificationLog.event_type == event_type)
        count_query = count_query.where(NotificationLog.event_type == event_type)
    if status:
        query = query.where(NotificationLog.status == status)
        count_query = count_query.where(NotificationLog.status == status)
    if project_id is not None:
        query = query.where(NotificationLog.project_id == project_id)
        count_query = count_query.where(NotificationLog.project_id == project_id)

    total = db.execute(count_query).scalar_one()
    logs = (
        db.execute(query.order_by(NotificationLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return PageResponse[NotificationLogResponse](data=logs, total=total, page=page, page_size=page_size)
