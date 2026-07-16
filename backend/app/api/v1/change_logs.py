"""接口变更历史 API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.change_log import InterfaceChangeLog
from app.schemas.common import DataResponse, PageResponse

router = APIRouter()


def _serialize_log(log: InterfaceChangeLog) -> dict:
    return {
        "id": log.id,
        "test_case_id": log.test_case_id,
        "action": log.action,
        "before": log.before,
        "after": log.after,
        "changed_fields": log.changed_fields,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("/{case_id}", response_model=PageResponse[dict])
def list_change_logs(
    case_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取某个接口的变更历史（按时间倒序）."""
    base_filter = InterfaceChangeLog.test_case_id == case_id
    total = db.execute(
        select(func.count())
        .select_from(InterfaceChangeLog)
        .where(base_filter)
    ).scalar_one()

    items = (
        db.execute(
            select(InterfaceChangeLog)
            .where(base_filter)
            .order_by(desc(InterfaceChangeLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_log(i) for i in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.get("", response_model=PageResponse[dict])
def list_all_change_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取所有接口变更历史（按时间倒序）。"""
    total = db.execute(
        select(func.count()).select_from(InterfaceChangeLog)
    ).scalar_one()
    items = (
        db.execute(
            select(InterfaceChangeLog)
            .order_by(desc(InterfaceChangeLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_log(i) for i in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)
