"""定时任务管理 API."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models import TestCase
from app.models.scheduled_task import ScheduledTask
from app.models.test_run_summary import TestRunSummary
from app.schemas.common import DataResponse, PageResponse

router = APIRouter()


class ScheduledTaskCreate(BaseModel):
    name: str
    mode: str = "interval"
    schedule_config: str
    case_ids: list[str] = []
    project_id: str | None = None
    is_enabled: bool = True


class ScheduledTaskUpdate(BaseModel):
    name: str | None = None
    mode: str | None = None
    schedule_config: str | None = None
    case_ids: list[str] | None = None
    project_id: str | None = None
    is_enabled: bool | None = None


def _serialize_task(t: ScheduledTask) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "mode": t.mode,
        "schedule_config": t.schedule_config,
        "case_ids": t.case_ids,
        "project_id": t.project_id,
        "is_enabled": t.is_enabled,
        "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
        "last_run_status": t.last_run_status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "case_count": len(t.case_ids) if t.case_ids else 0,
    }


@router.get("", response_model=PageResponse[dict])
def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """定时任务列表分页."""
    total = db.execute(select(func.count()).select_from(ScheduledTask)).scalar_one()
    tasks = (
        db.execute(
            select(ScheduledTask)
            .order_by(ScheduledTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_task(t) for t in tasks]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("", response_model=DataResponse[dict])
def create_task(payload: ScheduledTaskCreate, db: Session = Depends(get_db)):
    """创建定时任务."""
    task = ScheduledTask(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return DataResponse(data={"id": task.id, "name": task.name})


@router.put("/{task_id}", response_model=DataResponse[dict])
def update_task(task_id: str, payload: ScheduledTaskUpdate, db: Session = Depends(get_db)):
    """更新定时任务."""
    task = db.get(ScheduledTask, task_id)
    if not task:
        raise NotFoundError("定时任务", task_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    return DataResponse(data={"id": task.id, "name": task.name})


@router.delete("/{task_id}", response_model=DataResponse[dict])
def delete_task(task_id: str, db: Session = Depends(get_db)):
    """删除定时任务."""
    task = db.get(ScheduledTask, task_id)
    if not task:
        raise NotFoundError("定时任务", task_id)
    db.delete(task)
    db.commit()
    return DataResponse(data={"id": task_id, "deleted": True})


@router.post("/{task_id}/toggle", response_model=DataResponse[dict])
def toggle_task(task_id: str, db: Session = Depends(get_db)):
    """启用/停用定时任务."""
    task = db.get(ScheduledTask, task_id)
    if not task:
        raise NotFoundError("定时任务", task_id)
    task.is_enabled = not task.is_enabled
    db.commit()
    return DataResponse(data={"id": task.id, "is_enabled": task.is_enabled})


@router.post("/{task_id}/run", response_model=DataResponse[dict])
def run_task_now(task_id: str, db: Session = Depends(get_db)):
    """手动触发执行定时任务."""
    task = db.get(ScheduledTask, task_id)
    if not task:
        raise NotFoundError("定时任务", task_id)

    from test_engine.executor import TestCaseExecutor
    from app.schemas.execution import RequestDefinition

    _executor = TestCaseExecutor()

    run_id = str(_uuid.uuid4())
    passed, failed, errored = 0, 0, 0
    results = []
    case_ids = task.case_ids or []

    for case_id in case_ids:
        case = db.get(TestCase, case_id)
        if not case:
            errored += 1
            results.append({
                "case_id": case_id,
                "title": "(已删除)",
                "status": "error",
                "error": "用例不存在",
            })
            continue
        try:
            req_def = RequestDefinition(
                method=case.method,
                url=case.url,
                headers=dict(case.headers or {}),
                params=dict(case.params or {}),
                body=case.body,
                graphql_query=case.graphql_query,
                files=list(case.files) if case.files else None,
                extract_rules=list(case.extract_rules or []),
                timeout=30.0,
            )
            result = _executor.execute(
                request_def=req_def,
                assertions=[a.__dict__ for a in case.assertions],
                variables={},
            )
            status = result.status
            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
            else:
                errored += 1
            results.append({
                "case_id": case_id,
                "title": case.title,
                "method": case.method,
                "url": case.url,
                "status": status,
                "duration": round(result.duration, 4),
                "status_code": result.response.status_code if result.response else None,
                "error": result.error_message,
            })
        except Exception as exc:
            errored += 1
            results.append({
                "case_id": case_id,
                "title": case.title,
                "status": "error",
                "error": str(exc),
            })

    # 保存执行记录
    task.last_run_at = datetime.now()
    task.last_run_status = "passed" if passed == len(case_ids) else "failed"

    summary = TestRunSummary(
        run_id=run_id,
        source="scheduled",
        project_id=task.project_id,
        total=len(case_ids),
        passed=passed,
        failed=failed,
        error=errored,
        skipped=0,
        duration=sum(r.get("duration", 0) for r in results),
        triggered_by=f"scheduled_task:{task.name}",
        scheduled_task_id=task_id,
        summary={"results": results},
    )
    db.add(summary)
    db.commit()

    return DataResponse(data={
        "run_id": run_id,
        "total": len(case_ids),
        "passed": passed,
        "failed": failed,
        "error": errored,
        "results": results,
    })
