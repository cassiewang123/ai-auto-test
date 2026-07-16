"""审计日志查询 API (SEC-09).

仅超级管理员可访问，支持按 action / resource_type / actor_name / 时间范围筛选。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.common import PageResponse
from app.services.auth_service import require_superuser

router = APIRouter()


def _serialize_log(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "actor_id": log.actor_id,
        "actor_name": log.actor_name,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "project_id": log.project_id,
        "request_id": log.request_id,
        "source_ip": log.source_ip,
        "user_agent": log.user_agent,
        "before": log.before,
        "after": log.after,
        "result": log.result,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("", response_model=PageResponse[dict])
def list_audit_logs(
    action: str | None = Query(None, description="按操作类型筛选"),
    resource_type: str | None = Query(None, description="按资源类型筛选"),
    actor_name: str | None = Query(None, description="按操作人用户名筛选"),
    start_time: datetime | None = Query(None, description="起始时间 (ISO 8601)"),
    end_time: datetime | None = Query(None, description="结束时间 (ISO 8601)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_superuser),
):
    """分页查询审计日志（需超级管理员权限）。

    支持按 action / resource_type / actor_name / 时间范围组合筛选。
    """
    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)

    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)
    if actor_name:
        stmt = stmt.where(AuditLog.actor_name == actor_name)
        count_stmt = count_stmt.where(AuditLog.actor_name == actor_name)
    if start_time:
        stmt = stmt.where(AuditLog.created_at >= start_time)
        count_stmt = count_stmt.where(AuditLog.created_at >= start_time)
    if end_time:
        stmt = stmt.where(AuditLog.created_at <= end_time)
        count_stmt = count_stmt.where(AuditLog.created_at <= end_time)

    total = db.execute(count_stmt).scalar_one()
    items = (
        db.execute(
            stmt.order_by(desc(AuditLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_log(i) for i in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)
