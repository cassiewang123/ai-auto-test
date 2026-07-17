"""Normalized reporting helpers for unified execution jobs."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.execution_job import ExecutionJob, JobEvent
from app.models.user import User
from app.services.project_access import scope_project_resources
from app.services.security.data_redaction import redact_sensitive_data

RESULT_METRICS_CONFIG_KEY = "_result_metrics"
REPORTABLE_JOB_STATUSES = ("succeeded", "failed", "cancelled", "timed_out")


def scoped_execution_jobs(
    user: User,
    *,
    project_id: str | None = None,
    reportable_only: bool = True,
):
    """Build a project-scoped ExecutionJob query for reporting APIs."""
    stmt = scope_project_resources(select(ExecutionJob), ExecutionJob, user)
    if project_id is not None:
        stmt = stmt.where(ExecutionJob.project_id == project_id)
    if reportable_only:
        stmt = stmt.where(ExecutionJob.status.in_(REPORTABLE_JOB_STATUSES))
    return stmt


def _as_non_negative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _as_non_negative_float(value: Any) -> float:
    try:
        return max(float(value or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_event_payload(event: JobEvent | None) -> dict[str, Any]:
    if not event or not event.payload:
        return {}
    try:
        payload = json.loads(event.payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_event_payload(
    db: Session,
    job_id: str,
    event_types: tuple[str, ...],
) -> dict[str, Any]:
    event = (
        db.execute(
            select(JobEvent)
            .where(
                JobEvent.job_id == job_id,
                JobEvent.event_type.in_(event_types),
            )
            .order_by(desc(JobEvent.sequence))
            .limit(1)
        )
        .scalars()
        .first()
    )
    return _parse_event_payload(event)


def _status_counts(status: str, total: int) -> tuple[int, int, int, int]:
    if status == "succeeded":
        return total, 0, 0, 0
    if status == "cancelled":
        return 0, 0, 0, total
    if status == "timed_out":
        return 0, 0, total, 0
    return 0, total, 0, 0


def _fallback_metrics_from_event(
    job: ExecutionJob,
    payload: dict[str, Any],
) -> dict[str, Any]:
    duration = _as_non_negative_float(payload.get("duration"))

    if job.job_type == "ui_case" and "total_steps" in payload:
        total = _as_non_negative_int(payload.get("total_steps"))
        passed = _as_non_negative_int(payload.get("passed_steps"))
        failed = _as_non_negative_int(payload.get("failed_steps"))
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "error": max(total - passed - failed, 0),
            "skipped": 0,
            "duration": duration,
            "status_code": None,
        }

    if job.job_type == "ui_suite" and "total" in payload:
        total = _as_non_negative_int(payload.get("total"))
        passed = _as_non_negative_int(payload.get("passed"))
        failed = _as_non_negative_int(payload.get("failed"))
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "error": max(total - passed - failed, 0),
            "skipped": 0,
            "duration": duration,
            "status_code": None,
        }

    if job.job_type == "performance" and "total_requests" in payload:
        total = _as_non_negative_int(payload.get("total_requests"))
        passed = _as_non_negative_int(payload.get("success_requests"))
        failed = _as_non_negative_int(payload.get("fail_requests"))
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "error": max(total - passed - failed, 0),
            "skipped": 0,
            "duration": duration,
            "status_code": None,
            "p95": payload.get("p95"),
            "rps": payload.get("rps"),
        }

    total = 1
    passed, failed, error, skipped = _status_counts(job.status, total)
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "error": error,
        "skipped": skipped,
        "duration": duration,
        "status_code": payload.get("status_code"),
    }


def _job_duration(job: ExecutionJob) -> float:
    if not job.started_at or not job.finished_at:
        return 0.0
    try:
        return max((job.finished_at - job.started_at).total_seconds(), 0.0)
    except TypeError:
        return 0.0


def get_job_metrics(db: Session, job: ExecutionJob) -> dict[str, Any]:
    """Load persisted metrics, with JobEvent fallback for pre-upgrade jobs."""
    config = job.config if isinstance(job.config, dict) else {}
    metrics = config.get(RESULT_METRICS_CONFIG_KEY)
    if isinstance(metrics, dict):
        normalized = dict(metrics)
    else:
        terminal_payload = _latest_event_payload(
            db,
            job.id,
            ("job.completed", "job.failed", "job.timed_out"),
        )
        event_metrics = terminal_payload.get("metrics")
        if isinstance(event_metrics, dict):
            normalized = dict(event_metrics)
        else:
            log_payload = _latest_event_payload(db, job.id, ("job.log",))
            normalized = _fallback_metrics_from_event(job, log_payload)
            if not normalized.get("duration"):
                normalized["duration"] = terminal_payload.get("duration")

    total = _as_non_negative_int(normalized.get("total"))
    passed = _as_non_negative_int(normalized.get("passed"))
    failed = _as_non_negative_int(normalized.get("failed"))
    error = _as_non_negative_int(normalized.get("error"))
    skipped = _as_non_negative_int(normalized.get("skipped"))
    if total == 0 and job.status in REPORTABLE_JOB_STATUSES:
        total = 1
        passed, failed, error, skipped = _status_counts(job.status, total)

    return redact_sensitive_data(
        {
            **normalized,
            "total": total,
            "passed": min(passed, total),
            "failed": min(failed, total),
            "error": min(error, total),
            "skipped": min(skipped, total),
            "duration": round(
                _as_non_negative_float(normalized.get("duration"))
                or _job_duration(job),
                4,
            ),
        }
    )


def _resource_snapshot(db: Session, job: ExecutionJob) -> dict[str, Any]:
    if not job.resource_id:
        return {
            "title": job.job_type,
            "method": job.job_type.upper(),
            "url": f"job://{job.id}",
        }

    if job.job_type == "api_case":
        from app.models.test_case import TestCase

        resource = db.get(TestCase, job.resource_id)
        if resource:
            return {
                "title": resource.title,
                "method": resource.method,
                "url": resource.url,
                "headers": resource.headers,
                "params": resource.params,
                "body": resource.body,
            }
    elif job.job_type == "ui_case":
        from app.models.ui_test_case import UiTestCase

        resource = db.get(UiTestCase, job.resource_id)
        if resource:
            return {
                "title": resource.title,
                "method": "UI",
                "url": resource.url,
                "body": {"browser_type": resource.browser_type, "steps": resource.steps},
            }
    elif job.job_type == "ui_suite":
        from app.models.ui_test_suite import UiTestSuite

        resource = db.get(UiTestSuite, job.resource_id)
        if resource:
            return {
                "title": resource.name,
                "method": "UI",
                "url": f"ui-suite://{resource.name}",
                "body": {"case_ids": resource.case_ids},
            }
    elif job.job_type == "performance":
        from app.models.performance_test import PerformanceTest

        resource = db.get(PerformanceTest, job.resource_id)
        if resource:
            return {
                "title": resource.name,
                "method": "PERF",
                "url": f"performance://{resource.name}",
                "body": resource.config,
            }

    return {
        "title": f"{job.job_type}:{job.resource_id}",
        "method": job.job_type.upper(),
        "url": f"resource://{job.resource_id}",
    }


def normalize_job_run(
    db: Session,
    job: ExecutionJob,
    *,
    include_results: bool = False,
) -> dict[str, Any]:
    """Convert an ExecutionJob into the common report/history contract."""
    metrics = get_job_metrics(db, job)
    resource = _resource_snapshot(db, job)
    total = metrics["total"]
    passed = metrics["passed"]
    status = {
        "succeeded": "passed",
        "failed": "failed",
        "timed_out": "error",
        "cancelled": "skipped",
    }.get(job.status, job.status)

    run = {
        "run_id": job.id,
        "job_id": job.id,
        "project_id": job.project_id,
        "source": job.job_type,
        "job_type": job.job_type,
        "resource_id": job.resource_id,
        "total": total,
        "passed": passed,
        "failed": metrics["failed"],
        "error": metrics["error"],
        "skipped": metrics["skipped"],
        "duration": metrics["duration"],
        "created_at": job.started_at or job.created_at,
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "status": status,
        "job_status": job.status,
        "summary": job.result_summary,
        "error_message": job.error_message,
        "title": resource["title"],
        "method": resource["method"],
        "url": resource["url"],
        "status_code": metrics.get("status_code"),
        "headers": resource.get("headers"),
        "params": resource.get("params"),
        "body": resource.get("body"),
        "metrics": metrics,
    }
    if include_results:
        results = metrics.get("results")
        if not isinstance(results, list):
            results = [
                {
                    "case_id": job.resource_id,
                    "title": resource["title"],
                    "method": resource["method"],
                    "url": resource["url"],
                    "status": status,
                    "duration": metrics["duration"],
                    "status_code": metrics.get("status_code"),
                    "error": job.error_message,
                }
            ]
        run["results"] = results
    return redact_sensitive_data(run)


def sort_created_at(run: dict[str, Any]) -> datetime:
    value = run.get("created_at")
    return value if isinstance(value, datetime) else datetime.min
