"""历史调用记录 API：记录快速测试与用例执行的全部调用历史.

端点：
    GET /api/v1/history              — 分页查询历史记录（支持按状态/方法/URL 筛选）
    GET /api/v1/history/{record_id}  — 获取单条历史记录详情
    DELETE /api/v1/history/{record_id} — 删除单条历史记录
    DELETE /api/v1/history            — 清空全部历史记录
    GET /api/v1/history/stats         — 统计信息（总数、通过率、平均耗时）
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.call_history import CallHistory
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)
from app.services.security.data_redaction import redact_sensitive_data

router = APIRouter()


def _serialize(record: CallHistory) -> dict[str, Any]:
    """序列化历史记录."""
    return cast(
        dict[str, Any],
        redact_sensitive_data(
            {
                "id": record.id,
                "method": record.method,
                "url": record.url,
                "status_code": record.status_code,
                "status": record.status,
                "duration": record.duration,
                "has_files": record.has_files,
                "source": record.source,
                "test_case_id": record.test_case_id,
                "project_id": record.project_id,
                "created_by": record.created_by,
                "error_message": record.error_message,
                "executed_at": (record.executed_at.isoformat() if record.executed_at else None),
                # 详情字段
                "headers": record.headers,
                "params": record.params,
                "body": record.body,
                "response_headers": record.response_headers,
                "response_body": record.response_body,
                "response_text": record.response_text,
                "assertion_results": record.assertion_results,
                "pre_request_results": record.pre_request_results,
            }
        ),
    )


def save_history(
    db: Session,
    *,
    method: str,
    url: str,
    status: str,
    duration: float,
    headers: dict | None = None,
    params: dict | None = None,
    body: dict | None = None,
    status_code: int | None = None,
    response_headers: dict | None = None,
    response_body: Any | None = None,
    response_text: str | None = None,
    assertion_results: list | None = None,
    error_message: str | None = None,
    pre_request_results: list | None = None,
    has_files: bool = False,
    source: str = "quick_test",
    test_case_id: str | None = None,
    project_id: str | None = None,
    created_by: str | None = None,
) -> CallHistory:
    """保存一条历史调用记录（供 execution API 调用）."""
    safe_data = redact_sensitive_data(
        {
            "headers": headers,
            "params": params,
            "body": body,
            "response_headers": response_headers,
            "response_body": response_body,
            "response_text": response_text[:5000] if response_text else None,
            "assertion_results": assertion_results,
            "error_message": error_message,
            "pre_request_results": pre_request_results,
        }
    )
    record = CallHistory(
        method=method,
        url=url,
        status=status,
        duration=round(duration, 4),
        headers=safe_data["headers"],
        params=safe_data["params"],
        body=safe_data["body"],
        status_code=status_code,
        response_headers=safe_data["response_headers"],
        response_body=safe_data["response_body"],
        response_text=safe_data["response_text"],
        assertion_results=safe_data["assertion_results"],
        error_message=safe_data["error_message"],
        pre_request_results=safe_data["pre_request_results"],
        has_files=has_files,
        source=source,
        test_case_id=test_case_id,
        project_id=project_id,
        created_by=created_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=PageResponse[dict])
def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    method: str | None = Query(None),
    url: str | None = Query(None),
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页查询历史调用记录."""
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")

    stmt = scope_project_resources(
        select(CallHistory),
        CallHistory,
        current_user,
    )
    if status:
        stmt = stmt.where(CallHistory.status == status)
    if method:
        stmt = stmt.where(CallHistory.method == method.upper())
    if url:
        stmt = stmt.where(CallHistory.url.ilike(f"%{url}%"))
    if project_id is not None:
        stmt = stmt.where(CallHistory.project_id == project_id)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    records = (
        db.execute(stmt.order_by(CallHistory.executed_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )

    return PageResponse(
        data=[_serialize(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DataResponse[dict])
def get_stats(
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """统计信息：总数、各状态数、平均耗时."""
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")

    stmt = scope_project_resources(
        select(CallHistory),
        CallHistory,
        current_user,
    )
    if project_id is not None:
        stmt = stmt.where(CallHistory.project_id == project_id)
    scoped = stmt.subquery()
    row = db.execute(
        select(
            func.count().label("total"),
            func.sum(case((scoped.c.status == "passed", 1), else_=0)).label("passed"),
            func.sum(case((scoped.c.status == "failed", 1), else_=0)).label("failed"),
            func.sum(case((scoped.c.status == "error", 1), else_=0)).label("errored"),
            func.avg(scoped.c.duration).label("avg_duration"),
        )
    ).one()
    total = int(row.total or 0)
    passed = int(row.passed or 0)
    failed = int(row.failed or 0)
    errored = int(row.errored or 0)
    avg_duration = float(row.avg_duration or 0)

    return DataResponse(
        data={
            "total": total,
            "passed": passed,
            "failed": failed,
            "error": errored,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
            "avg_duration": round(float(avg_duration), 4),
        }
    )


@router.get("/{record_id}", response_model=DataResponse[dict])
def get_history(
    record_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单条历史记录详情."""
    record = db.query(CallHistory).filter(CallHistory.id == record_id).first()
    if not record:
        raise NotFoundError("CallHistory", record_id)
    ensure_resource_role(db, current_user, record, "viewer")
    return DataResponse(data=_serialize(record))


@router.delete("/{record_id}", response_model=DataResponse[dict])
def delete_history(
    record_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除单条历史记录."""
    record = db.query(CallHistory).filter(CallHistory.id == record_id).first()
    if not record:
        raise NotFoundError("CallHistory", record_id)
    ensure_resource_role(db, current_user, record, "admin")
    db.delete(record)
    db.commit()
    return DataResponse(data={"deleted": True})


@router.delete("", response_model=DataResponse[dict])
def clear_history(
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清空当前用户可管理的历史记录."""
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "admin")

    stmt = scope_project_resources(
        select(CallHistory.id),
        CallHistory,
        current_user,
        minimum_role="admin",
    )
    if project_id is not None:
        stmt = stmt.where(CallHistory.project_id == project_id)
    record_ids = list(db.execute(stmt).scalars().all())
    deleted = 0
    if record_ids:
        deleted = db.query(CallHistory).filter(CallHistory.id.in_(record_ids)).delete(synchronize_session=False)
    db.commit()
    return DataResponse(data={"deleted_count": deleted})
