"""CI/CD 集成 API：CLI 触发执行、执行状态查询、Webhook 回调管理.

认证：通过 Authorization: Bearer air_xxx 或 X-API-Key header 携带 API Token。

端点：
    POST /ci/trigger                   — 触发执行（plan_id 或 case_ids）
    GET  /ci/runs/{run_id}/status      — 查询执行状态
    POST /ci/webhooks                  — 注册 webhook
    GET  /ci/webhooks                  — webhook 列表
    PUT  /ci/webhooks/{webhook_id}     — 更新 webhook
    DELETE /ci/webhooks/{webhook_id}   — 删除 webhook
    POST /ci/webhooks/{webhook_id}/test — 测试 webhook
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.database import get_db
from app.models.user import User
from app.schemas.ci_cd import (
    CiTriggerRequest,
    CiTriggerResponse,
    WebhookConfigCreate,
    WebhookConfigResponse,
    WebhookConfigUpdate,
)
from app.schemas.common import DataResponse, ResponseBase
from app.services.auth_service import get_current_user
from app.services.ci_cd_service import send_webhook, trigger_execution, validate_token
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


# ---------------------------------------------------------------------------
# 认证依赖
# ---------------------------------------------------------------------------


def _extract_token(authorization: str | None, x_api_key: str | None) -> str | None:
    """从 Authorization Bearer 或 X-API-Key 提取 token 字符串."""
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def authenticate_ci_token(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """认证依赖：校验 API Token 有效性（不含 scope 检查）."""

    token_str = _extract_token(authorization, x_api_key)
    if not token_str:
        raise AuthenticationError("缺少 API Token")
    return validate_token(db, token_str)


def _require_scope(token, scope: str) -> None:
    """检查 token 是否拥有指定 scope，否则抛出认证异常."""
    if scope not in (token.scopes or []):
        raise AuthenticationError(f"缺少权限: {scope}")


def _get_ci_token_user(db: Session, token) -> User | None:
    """Resolve the optional user binding carried by a CI token."""
    if not token.user_id:
        return None
    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        raise AuthenticationError("API Token 绑定用户无效")
    return user


def _authorize_ci_target(
    db: Session,
    token,
    req: CiTriggerRequest,
) -> tuple[str | None, User | None]:
    """Authorize a CI target and return its single project plus token actor."""
    from app.models import TestCase, TestPlan

    actor = _get_ci_token_user(db, token)
    if req.plan_id:
        plan = db.get(TestPlan, req.plan_id)
        if not plan:
            raise NotFoundError("测试计划", req.plan_id)
        if actor is not None:
            ensure_resource_role(db, actor, plan, "tester")
        elif plan.project_id is not None:
            raise ForbiddenError("CI Token must bind a project member")

        for item in plan.items:
            item_case = item.test_case
            if item_case is not None and item_case.project_id != plan.project_id:
                raise ValidationError("测试计划包含跨项目用例")
        return plan.project_id, actor

    cases: list[TestCase] = []
    for case_id in req.case_ids:
        case = db.get(TestCase, case_id)
        if not case:
            raise NotFoundError("测试用例", case_id)
        cases.append(case)

    project_ids = {case.project_id for case in cases}
    if len(project_ids) != 1:
        raise ValidationError("CI 触发的用例必须属于同一项目")
    project_id = next(iter(project_ids))
    if actor is not None:
        for case in cases:
            ensure_resource_role(
                db,
                actor,
                case,
                "tester",
                owner_field=None,
            )
    elif project_id is not None:
        raise ForbiddenError("CI Token must bind a project member")
    return project_id, actor


def _ensure_project_or_workspace_role(
    db: Session,
    user: User,
    project_id: str | None,
    minimum_role: str,
) -> None:
    """Authorize project configs; unscoped configs are workspace-admin only."""
    if user.is_superuser:
        return
    if not project_id:
        raise ForbiddenError("Workspace CI configuration requires superuser")
    ensure_project_role(db, user, project_id, minimum_role)


# ---------------------------------------------------------------------------
# Webhook 序列化
# ---------------------------------------------------------------------------


def _to_webhook_response(cfg) -> WebhookConfigResponse:
    return WebhookConfigResponse(
        id=cfg.id,
        name=cfg.name,
        url=mask_url(cfg.url),
        has_url=bool(cfg.url),
        events=list(cfg.events or []),
        has_secret=bool(cfg.secret),
        is_active=cfg.is_active,
        project_id=cfg.project_id,
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


def _sanitize_webhook_results(
    results: list[dict],
    *,
    stored_url: str | None,
) -> list[dict]:
    """Ensure test-send responses cannot expose stored or plaintext URLs."""
    sanitized: list[dict] = []
    for result in results:
        item = dict(result)
        result_url = item.get("url")
        item["url"] = mask_url(result_url or stored_url)
        item["has_url"] = bool(result_url or stored_url)
        if item.get("error"):
            item["error"] = redact_url_from_text(
                str(item["error"]),
                stored_url,
                str(result_url) if result_url else None,
            )
        sanitized.append(item)
    return sanitized


def _get_webhook_or_404(db: Session, webhook_id: str):
    from app.models.webhook_config import WebhookConfig

    cfg = db.get(WebhookConfig, webhook_id)
    if not cfg:
        raise NotFoundError("Webhook", webhook_id)
    return cfg


# ---------------------------------------------------------------------------
# 后台任务：执行完成后异步发送 webhook
# ---------------------------------------------------------------------------


def _notify_webhooks(event: str, payload: dict) -> None:
    """后台任务：向匹配的 Webhook 发送回调。使用独立 DB Session."""
    from app.database import SessionLocal
    from app.models.webhook_config import WebhookConfig

    db = SessionLocal()
    try:
        project_id = payload.get("project_id")
        query = db.query(WebhookConfig).filter(WebhookConfig.is_active.is_(True))
        if project_id is None:
            query = query.filter(WebhookConfig.project_id.is_(None))
        else:
            query = query.filter(
                or_(
                    WebhookConfig.project_id == project_id,
                    WebhookConfig.project_id.is_(None),
                )
            )
        for cfg in query.all():
            if event not in (cfg.events or []):
                continue
            send_webhook(
                db,
                event,
                payload,
                only_webhook_id=cfg.id,
            )
    except Exception:  # noqa: BLE001 - 后台任务不应抛出
        pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CI 触发
# ---------------------------------------------------------------------------


@router.post("/trigger", response_model=DataResponse[CiTriggerResponse])
def ci_trigger(
    req: CiTriggerRequest,
    background_tasks: BackgroundTasks,
    token=Depends(authenticate_ci_token),
    db: Session = Depends(get_db),
):
    """触发执行：支持 plan_id（需 test-plans:execute）或 case_ids（需 test-cases:execute）。

    执行完成后异步发送 webhook 回调（test_run.completed / test_run.failed）。
    """
    if req.plan_id:
        _require_scope(token, "test-plans:execute")
    else:
        _require_scope(token, "test-cases:execute")

    project_id, actor = _authorize_ci_target(db, token, req)
    if req.plan_id:
        result = trigger_execution(db, plan_id=req.plan_id, environment_id=req.environment_id, source="ci")
    else:
        result = trigger_execution(db, case_ids=req.case_ids, environment_id=req.environment_id, source="ci")

    from app.models import TestRunSummary

    summary = db.execute(select(TestRunSummary).where(TestRunSummary.run_id == result["run_id"])).scalar_one_or_none()
    if summary is not None:
        summary.project_id = project_id
        summary.created_by = actor.id if actor is not None else None
        db.commit()

    # 异步发送 webhook 回调
    event = "test_run.completed" if result["status"] == "passed" else "test_run.failed"
    background_tasks.add_task(
        _notify_webhooks,
        event,
        {
            "event": event,
            "run_id": result["run_id"],
            "status": result["status"],
            "total": result["total"],
            "passed": result["passed"],
            "failed": result["failed"],
            "error": result["error"],
            "project_id": project_id,
            "triggered_at": datetime.now().isoformat(),
        },
    )

    return DataResponse(
        data=CiTriggerResponse(
            run_id=result["run_id"],
            status=result["status"],
            message=result["message"],
            total=result["total"],
            passed=result["passed"],
            failed=result["failed"],
            error=result["error"],
        )
    )


@router.get("/runs/{run_id}/status", response_model=DataResponse[dict])
def get_run_status(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询某次执行的汇总状态（需 JWT 鉴权）."""
    from app.models import TestRunSummary

    summary = db.query(TestRunSummary).filter(TestRunSummary.run_id == run_id).first()
    if not summary:
        raise NotFoundError("执行记录", run_id)
    ensure_resource_role(db, current_user, summary, "viewer")
    status = "passed" if summary.failed == 0 and summary.error == 0 else "failed"
    return DataResponse(
        data={
            "run_id": run_id,
            "status": status,
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "error": summary.error,
            "skipped": summary.skipped,
            "duration": summary.duration,
            "source": summary.source,
            "project_id": summary.project_id,
            "created_at": summary.created_at.isoformat() if summary.created_at else None,
        }
    )


# ---------------------------------------------------------------------------
# Webhook CRUD
# ---------------------------------------------------------------------------


@router.post("/webhooks", response_model=DataResponse[WebhookConfigResponse])
def create_webhook(
    payload: WebhookConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """注册 Webhook 配置（需 JWT 鉴权）."""
    from app.models.webhook_config import WebhookConfig

    _ensure_project_or_workspace_role(
        db,
        current_user,
        payload.project_id,
        "developer",
    )
    try:
        encrypted_url = prepare_url_for_storage(
            payload.url,
            max_ciphertext_length=2048,
        )
        encrypted_secret = encrypt_secret(
            payload.secret,
            max_ciphertext_length=256,
        )
    except (SecretCryptoError, TypeError) as exc:
        raise ValidationError(f"Webhook 敏感配置加密失败: {exc}") from exc

    cfg = WebhookConfig(
        name=payload.name,
        url=encrypted_url or "",
        events=list(payload.events),
        secret=encrypted_secret or "",
        is_active=payload.is_active,
        project_id=payload.project_id,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return DataResponse(data=_to_webhook_response(cfg))


@router.get("/webhooks", response_model=DataResponse[list[WebhookConfigResponse]])
def list_webhooks(
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户可访问的 Webhook 配置."""
    from app.models.webhook_config import WebhookConfig

    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    stmt = scope_project_resources(
        select(WebhookConfig),
        WebhookConfig,
        current_user,
        owner_field=None,
    )
    if project_id is not None:
        stmt = stmt.where(WebhookConfig.project_id == project_id)
    configs = db.execute(stmt.order_by(WebhookConfig.created_at.desc())).scalars().all()
    return DataResponse(data=[_to_webhook_response(c) for c in configs])


@router.get(
    "/webhooks/{webhook_id}",
    response_model=DataResponse[WebhookConfigResponse],
)
def get_webhook(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个 Webhook 配置."""
    cfg = _get_webhook_or_404(db, webhook_id)
    ensure_resource_role(
        db,
        current_user,
        cfg,
        "viewer",
        owner_field=None,
    )
    return DataResponse(data=_to_webhook_response(cfg))


@router.put("/webhooks/{webhook_id}", response_model=DataResponse[WebhookConfigResponse])
def update_webhook(
    webhook_id: str,
    payload: WebhookConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 Webhook 配置（部分更新，需 JWT 鉴权）."""
    cfg = _get_webhook_or_404(db, webhook_id)
    ensure_resource_role(
        db,
        current_user,
        cfg,
        "developer",
        owner_field=None,
    )
    update_data = payload.model_dump(exclude_unset=True)
    if "project_id" in update_data and update_data["project_id"] != cfg.project_id:
        ensure_resource_role(
            db,
            current_user,
            cfg,
            "admin",
            owner_field=None,
        )
        _ensure_project_or_workspace_role(
            db,
            current_user,
            update_data["project_id"],
            "admin",
        )
    if "secret" in update_data:
        try:
            update_data["secret"] = encrypt_secret(
                update_data["secret"],
                max_ciphertext_length=256,
            )
        except (SecretCryptoError, TypeError) as exc:
            raise ValidationError(f"Webhook 密钥加密失败: {exc}") from exc
    if "url" in update_data:
        if update_data["url"] is None:
            raise ValidationError("Webhook URL 不能为空")
        try:
            update_data["url"] = prepare_url_for_storage(
                update_data["url"],
                existing=cfg.url,
                max_ciphertext_length=2048,
            )
        except (SecretCryptoError, TypeError) as exc:
            raise ValidationError(f"Webhook URL 加密失败: {exc}") from exc
    for field, value in update_data.items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    return DataResponse(data=_to_webhook_response(cfg))


@router.delete("/webhooks/{webhook_id}", response_model=ResponseBase)
def delete_webhook(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 Webhook 配置（需 JWT 鉴权）."""
    cfg = _get_webhook_or_404(db, webhook_id)
    ensure_resource_role(
        db,
        current_user,
        cfg,
        "admin",
        owner_field=None,
    )
    db.delete(cfg)
    db.commit()
    return ResponseBase()


@router.post("/webhooks/{webhook_id}/test", response_model=DataResponse[dict])
def test_webhook(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """向指定 Webhook 发送一次测试回调（需 JWT 鉴权）."""
    cfg = _get_webhook_or_404(db, webhook_id)
    ensure_resource_role(
        db,
        current_user,
        cfg,
        "tester",
        owner_field=None,
    )
    payload = {
        "event": "ping",
        "message": "AIRETEST webhook 测试",
        "webhook_id": webhook_id,
        "sent_at": datetime.now().isoformat(),
    }
    results = send_webhook(db, "ping", payload, only_webhook_id=webhook_id)
    results = _sanitize_webhook_results(results, stored_url=cfg.url)
    return DataResponse(
        data={
            "webhook_id": webhook_id,
            "sent": any(r.get("success") for r in results),
            "results": results,
        }
    )
