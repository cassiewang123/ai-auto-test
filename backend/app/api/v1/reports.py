"""测试报告 API.

提供两套报告能力：
1. 以 ExecutionJob 为主、合并 TestRunSummary 的近期执行报告；
2. 基于 TestResult 明细的旧版查询、汇总与历史趋势。
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models import TestCase, TestResult
from app.models.execution_job import ExecutionJob
from app.models.test_run_summary import TestRunSummary
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.schemas.test_result import (
    TestResultResponse,
    TrendPoint,
)
from app.schemas.test_result import (
    TestRunSummary as TestRunSummarySchema,
)
from app.services.auth_service import get_current_user
from app.services.execution.job_reporting import (
    normalize_job_run,
    scoped_execution_jobs,
    sort_created_at,
)
from app.services.project_access import (
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)
from app.services.security.data_redaction import redact_sensitive_data

router = APIRouter()

_REPORTABLE_JOB_STATUSES = {"succeeded", "failed", "cancelled", "timed_out"}


def _status_sum(status: str):
    """构造某状态的计数表达式。"""
    return func.sum(case((TestResult.status == status, 1), else_=0))


def _get_run_summary(
    db: Session,
    run_id: str,
) -> TestRunSummary | None:
    return cast(
        TestRunSummary | None,
        db.execute(select(TestRunSummary).where(TestRunSummary.run_id == run_id)).scalar_one_or_none(),
    )


def _ensure_run_access(
    db: Session,
    user: User,
    run_id: str,
) -> TestRunSummary | None:
    """Authorize a run; superusers retain access to result-only legacy runs."""
    summary = _get_run_summary(db, run_id)
    if summary is None:
        if user.is_superuser:
            return None
        raise NotFoundError("执行记录", run_id)
    ensure_resource_role(db, user, summary, "viewer")
    return summary


def _scoped_run_statement(
    user: User,
    *,
    project_id: str | None = None,
):
    stmt = scope_project_resources(
        select(TestRunSummary),
        TestRunSummary,
        user,
    )
    if project_id is not None:
        stmt = stmt.where(TestRunSummary.project_id == project_id)
    return stmt


def _legacy_result_details(db: Session, run_id: str) -> list[dict]:
    results = db.execute(select(TestResult).where(TestResult.run_id == run_id)).scalars().all()
    detail_results = []
    for result in results:
        test_case = db.get(TestCase, result.test_case_id)
        detail_results.append(
            {
                "case_id": result.test_case_id,
                "title": test_case.title if test_case else "(已删除)",
                "method": test_case.method if test_case else "",
                "url": test_case.url if test_case else "",
                "status": result.status,
                "duration": round(result.duration, 4),
                "status_code": (
                    result.response_snapshot.get("status_code")
                    if result.response_snapshot
                    else None
                ),
                "error": result.error_message,
            }
        )
    return detail_results


def _normalize_legacy_run(
    db: Session,
    summary: TestRunSummary,
    *,
    include_results: bool = False,
) -> dict:
    total = summary.total or 0
    if summary.failed:
        status = "failed"
    elif summary.error:
        status = "error"
    elif total > 0 and summary.skipped == total:
        status = "skipped"
    else:
        status = "passed"

    run = {
        "run_id": summary.run_id,
        "project_id": summary.project_id,
        "source": summary.source,
        "total": total,
        "passed": summary.passed or 0,
        "failed": summary.failed or 0,
        "error": summary.error or 0,
        "skipped": summary.skipped or 0,
        "duration": round(summary.duration or 0.0, 3),
        "created_at": summary.created_at,
        "pass_rate": round((summary.passed or 0) / total * 100, 1) if total else 0.0,
        "status": status,
        "summary": summary.summary,
    }
    if include_results:
        run["results"] = _legacy_result_details(db, summary.run_id)
    return run


def _list_run_payload(run: dict) -> dict:
    """Return the stable, compact contract consumed by the reports page."""
    keys = (
        "run_id",
        "job_id",
        "project_id",
        "source",
        "job_type",
        "resource_id",
        "title",
        "total",
        "passed",
        "failed",
        "error",
        "skipped",
        "duration",
        "created_at",
        "pass_rate",
        "status",
        "job_status",
        "error_message",
    )
    return {key: run.get(key) for key in keys if key in run}


def _detail_payload(run: dict) -> dict:
    summary = _list_run_payload(run)
    if run.get("summary") is not None:
        summary["result_summary"] = run["summary"]
    return {
        "run_id": run["run_id"],
        "summary": summary,
        "results": run.get("results") or [],
    }


def _merged_runs(
    db: Session,
    user: User,
    *,
    project_id: str | None = None,
) -> list[dict]:
    """Merge reportable jobs with legacy summaries; ExecutionJob wins duplicates."""
    legacy_rows = (
        db.execute(
            _scoped_run_statement(
                user,
                project_id=project_id,
            )
        )
        .scalars()
        .all()
    )
    merged = {
        row.run_id: _normalize_legacy_run(db, row)
        for row in legacy_rows
    }

    jobs = (
        db.execute(
            scoped_execution_jobs(
                user,
                project_id=project_id,
                reportable_only=True,
            )
        )
        .scalars()
        .all()
    )
    for job in jobs:
        merged[job.id] = normalize_job_run(db, job)

    return sorted(merged.values(), key=sort_created_at, reverse=True)


# ---------------------------------------------------------------------------
# 统一执行任务与旧批次汇总的新报告接口
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=DataResponse[list])
def list_recent_runs(
    limit: int = Query(10, ge=1, le=100),
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取最近 N 次执行批次（用于趋势图）."""
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    runs = _merged_runs(db, current_user, project_id=project_id)[:limit]
    data = [_list_run_payload(run) for run in runs]
    return DataResponse(data=data)


@router.get("/runs/{run_id}", response_model=DataResponse[dict])
def get_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单次执行的详细信息（用于饼图和详情列表）."""
    job = db.get(ExecutionJob, run_id)
    if job is not None and job.status in _REPORTABLE_JOB_STATUSES:
        ensure_resource_role(db, current_user, job, "viewer")
        run = normalize_job_run(db, job, include_results=True)
        return DataResponse(data=redact_sensitive_data(_detail_payload(run)))

    summary = _get_run_summary(db, run_id)
    if not summary:
        if not current_user.is_superuser:
            raise NotFoundError("执行记录", run_id)
        return DataResponse(data={"error": "未找到执行记录"})
    ensure_resource_role(db, current_user, summary, "viewer")
    run = _normalize_legacy_run(db, summary, include_results=True)
    return DataResponse(data=redact_sensitive_data(_detail_payload(run)))


@router.get("/trend", response_model=DataResponse[dict])
def get_trend(
    limit: int = Query(10, ge=1, le=50),
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取趋势数据（近 N 次执行的通过率趋势）."""
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    runs = list(reversed(_merged_runs(db, current_user, project_id=project_id)[:limit]))
    data = {
        "labels": [
            run["created_at"].strftime("%m-%d %H:%M")
            if isinstance(run.get("created_at"), datetime)
            else ""
            for run in runs
        ],
        "pass_rates": [run.get("pass_rate", 0.0) for run in runs],
        "totals": [run.get("total", 0) for run in runs],
        "passed": [run.get("passed", 0) for run in runs],
        "failed": [
            run.get("failed", 0) + run.get("error", 0)
            for run in runs
        ],
    }
    return DataResponse(data=data)


# ---------------------------------------------------------------------------
# 基于 TestResult 明细的查询接口（保留原有能力）
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/results", response_model=PageResponse[TestResultResponse])
def list_run_results(
    run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按 run_id 查询执行结果列表（分页）。"""
    _ensure_run_access(db, current_user, run_id)
    base_filter = TestResult.run_id == run_id
    total = db.execute(select(func.count()).select_from(TestResult).where(base_filter)).scalar_one()

    items = (
        db.execute(
            select(TestResult)
            .where(base_filter)
            .order_by(TestResult.executed_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    safe_items = [redact_sensitive_data(TestResultResponse.model_validate(item).model_dump()) for item in items]
    return PageResponse[TestResultResponse](data=safe_items, total=total, page=page, page_size=page_size)


@router.get("/runs/{run_id}/summary", response_model=DataResponse[TestRunSummarySchema])
def get_run_summary(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回某 run_id 的汇总统计：total/passed/failed/skipped/duration_sum。"""
    _ensure_run_access(db, current_user, run_id)
    row = db.execute(
        select(
            func.count().label("total"),
            _status_sum("passed").label("passed"),
            _status_sum("failed").label("failed"),
            _status_sum("skipped").label("skipped"),
            func.coalesce(func.sum(TestResult.duration), 0.0).label("duration_sum"),
        ).where(TestResult.run_id == run_id)
    ).one()

    summary = TestRunSummarySchema(
        run_id=run_id,
        total=row.total or 0,
        passed=int(row.passed or 0),
        failed=int(row.failed or 0),
        skipped=int(row.skipped or 0),
        duration_sum=float(row.duration_sum or 0.0),
    )
    return DataResponse[TestRunSummarySchema](data=summary)


@router.get("/trends", response_model=DataResponse[list[TrendPoint]])
def get_trends(
    start: datetime = Query(..., description="起始时间（ISO 8601）"),
    end: datetime = Query(..., description="结束时间（ISO 8601）"),
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按时间范围查询历史趋势，按天聚合 total/passed/failed/skipped。"""
    date_col = func.date(TestResult.executed_at).label("date")
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")

    stmt = (
        select(
            date_col,
            func.count().label("total"),
            _status_sum("passed").label("passed"),
            _status_sum("failed").label("failed"),
            _status_sum("skipped").label("skipped"),
        )
        .where(TestResult.executed_at.between(start, end))
        .group_by(date_col)
        .order_by(date_col)
    )
    if not current_user.is_superuser or project_id is not None:
        run_ids = scope_project_resources(
            select(TestRunSummary.run_id),
            TestRunSummary,
            current_user,
        )
        if project_id is not None:
            run_ids = run_ids.where(TestRunSummary.project_id == project_id)
        stmt = stmt.where(TestResult.run_id.in_(run_ids))
    rows = db.execute(stmt).all()
    points = [
        TrendPoint(
            date=str(r.date),
            total=int(r.total or 0),
            passed=int(r.passed or 0),
            failed=int(r.failed or 0),
            skipped=int(r.skipped or 0),
        )
        for r in rows
    ]
    return DataResponse[list[TrendPoint]](data=points)
