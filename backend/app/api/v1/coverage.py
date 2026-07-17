"""API coverage statistics backed by legacy results and execution jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TestCase, TestResult
from app.models.test_run_summary import TestRunSummary
from app.models.user import User
from app.schemas.common import DataResponse
from app.services.auth_service import get_current_user
from app.services.execution.job_reporting import (
    normalize_job_run,
    scoped_execution_jobs,
    sort_created_at,
)
from app.services.project_access import (
    ensure_project_role,
    scope_project_resources,
)

router = APIRouter()

_UNGROUPED = "未分组"
_RECENT_RUN_LIMIT = 10


def _scoped_legacy_runs(
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


def _legacy_covered_case_ids(
    db: Session,
    user: User,
    *,
    project_id: str | None,
) -> set[str]:
    stmt = select(TestResult.test_case_id).join(
        TestCase,
        TestCase.id == TestResult.test_case_id,
    )
    if project_id is not None:
        stmt = stmt.where(TestCase.project_id == project_id)

    if not user.is_superuser:
        run_ids = scope_project_resources(
            select(TestRunSummary.run_id),
            TestRunSummary,
            user,
        )
        if project_id is not None:
            run_ids = run_ids.where(TestRunSummary.project_id == project_id)
        stmt = stmt.where(TestResult.run_id.in_(run_ids))

    return set(db.execute(stmt).scalars().all())


def _visible_cases(
    db: Session,
    user: User,
    *,
    project_id: str | None,
    referenced_case_ids: set[str],
) -> list[TestCase]:
    stmt = scope_project_resources(select(TestCase), TestCase, user)
    if project_id is not None:
        stmt = stmt.where(TestCase.project_id == project_id)
    cases = list(db.execute(stmt).scalars().all())

    # TestCase has no creator field. An unscoped legacy case is visible to a
    # non-superuser only when one of their scoped runs/jobs references it.
    if (
        not user.is_superuser
        and project_id is None
        and referenced_case_ids
    ):
        legacy_cases = (
            db.execute(
                select(TestCase).where(
                    TestCase.project_id.is_(None),
                    TestCase.id.in_(referenced_case_ids),
                )
            )
            .scalars()
            .all()
        )
        known_ids = {case.id for case in cases}
        cases.extend(case for case in legacy_cases if case.id not in known_ids)

    return cases


def _normalize_legacy_run(summary: TestRunSummary) -> dict[str, Any]:
    total = int(summary.total or 0)
    passed = int(summary.passed or 0)
    return {
        "run_id": summary.run_id,
        "project_id": summary.project_id,
        "source": summary.source,
        "total": total,
        "passed": passed,
        "failed": int(summary.failed or 0),
        "error": int(summary.error or 0),
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "created_at": summary.created_at,
    }


def _serialize_recent_run(run: dict[str, Any]) -> dict[str, Any]:
    created_at = run.get("created_at")
    return {
        "run_id": run["run_id"],
        "total": int(run.get("total") or 0),
        "passed": int(run.get("passed") or 0),
        "failed": int(run.get("failed") or 0),
        "error": int(run.get("error") or 0),
        "pass_rate": float(run.get("pass_rate") or 0.0),
        "created_at": (
            created_at.strftime("%m-%d %H:%M")
            if isinstance(created_at, datetime)
            else ""
        ),
    }


@router.get("", response_model=DataResponse[dict])
def get_coverage(
    project_id: str | None = Query(None, description="Filter by project"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return API endpoint coverage and recent unified execution runs."""
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")

    jobs = (
        db.execute(
            scoped_execution_jobs(
                current_user,
                project_id=project_id,
            )
        )
        .scalars()
        .all()
    )
    job_case_ids = {
        job.resource_id
        for job in jobs
        if job.job_type == "api_case" and job.resource_id
    }
    legacy_case_ids = _legacy_covered_case_ids(
        db,
        current_user,
        project_id=project_id,
    )
    covered_case_ids = legacy_case_ids | job_case_ids

    cases = _visible_cases(
        db,
        current_user,
        project_id=project_id,
        referenced_case_ids=covered_case_ids,
    )

    endpoint_groups: dict[tuple[str | None, str], set[str]] = {}
    endpoint_case_ids: dict[tuple[str | None, str], set[str]] = {}
    for case in cases:
        endpoint = (case.method, case.url)
        endpoint_groups.setdefault(endpoint, set()).add(
            case.group_path or _UNGROUPED
        )
        endpoint_case_ids.setdefault(endpoint, set()).add(case.id)

    endpoints = set(endpoint_case_ids)
    covered_endpoints = {
        endpoint
        for endpoint, case_ids in endpoint_case_ids.items()
        if case_ids & covered_case_ids
    }
    total_endpoints = len(endpoints)
    covered = len(covered_endpoints)
    coverage_rate = (
        round(covered / total_endpoints * 100, 1)
        if total_endpoints
        else 0.0
    )

    by_method_map: dict[str, dict[str, int]] = {}
    for endpoint in endpoints:
        method = endpoint[0] or "UNKNOWN"
        counts = by_method_map.setdefault(
            method,
            {"total": 0, "covered": 0},
        )
        counts["total"] += 1
        if endpoint in covered_endpoints:
            counts["covered"] += 1

    by_method = []
    for method, counts in sorted(by_method_map.items()):
        total = counts["total"]
        method_covered = counts["covered"]
        by_method.append(
            {
                "method": method,
                "total": total,
                "covered": method_covered,
                "uncovered": total - method_covered,
                "coverage_rate": (
                    round(method_covered / total * 100, 1)
                    if total
                    else 0.0
                ),
            }
        )

    by_group_map: dict[str, dict[str, int]] = {}
    for endpoint, groups in endpoint_groups.items():
        for group_path in groups:
            counts = by_group_map.setdefault(
                group_path,
                {"total": 0, "covered": 0},
            )
            counts["total"] += 1
            if endpoint in covered_endpoints:
                counts["covered"] += 1

    by_group = []
    for group_path, counts in by_group_map.items():
        total = counts["total"]
        group_covered = counts["covered"]
        by_group.append(
            {
                "group_path": group_path,
                "total": total,
                "covered": group_covered,
                "uncovered": total - group_covered,
                "coverage_rate": (
                    round(group_covered / total * 100, 1)
                    if total
                    else 0.0
                ),
            }
        )
    by_group.sort(key=lambda item: (-item["total"], item["group_path"]))

    legacy_runs = (
        db.execute(
            _scoped_legacy_runs(
                current_user,
                project_id=project_id,
            )
        )
        .scalars()
        .all()
    )
    runs_by_id = {
        summary.run_id: _normalize_legacy_run(summary)
        for summary in legacy_runs
    }
    for job in jobs:
        normalized = normalize_job_run(db, job)
        runs_by_id[normalized["run_id"]] = normalized

    recent_runs = sorted(
        runs_by_id.values(),
        key=sort_created_at,
        reverse=True,
    )[:_RECENT_RUN_LIMIT]
    recent_runs.reverse()

    return DataResponse(
        data={
            "total_endpoints": total_endpoints,
            "covered": covered,
            "uncovered": total_endpoints - covered,
            "coverage_rate": coverage_rate,
            "by_method": by_method,
            "by_group": by_group,
            "recent_runs": [
                _serialize_recent_run(run)
                for run in recent_runs
            ],
        }
    )
