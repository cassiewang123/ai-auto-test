"""ExecutionJob normalized metrics persistence and legacy fallback tests."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.models.execution_job import ExecutionJob, JobEvent
from app.services.execution.job_reporting import (
    RESULT_METRICS_CONFIG_KEY,
    get_job_metrics,
    normalize_job_run,
)
from app.services.execution.job_service import JobService


def test_execute_job_persists_metrics_in_config_and_terminal_event(
    db_session,
    monkeypatch,
):
    service = JobService(db_session)
    job = service.create_job(job_type="api_case")
    metrics = {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "error": 0,
        "skipped": 0,
        "duration": 0.25,
        "status_code": 200,
        "results": [{"title": "health", "status": "passed"}],
    }

    monkeypatch.setattr(
        JobService,
        "_run",
        lambda self, running_job: {
            "status": "succeeded",
            "summary": f"{running_job.id} completed",
            "metrics": metrics,
        },
    )

    completed = service.execute_job(job.id, worker_id="metrics-worker")

    assert completed.config[RESULT_METRICS_CONFIG_KEY] == metrics
    terminal = (
        db_session.query(JobEvent)
        .filter_by(job_id=job.id, event_type="job.completed")
        .one()
    )
    assert json.loads(terminal.payload)["metrics"] == metrics


@pytest.mark.parametrize(
    ("job_type", "payload", "expected"),
    [
        (
            "api_case",
            {"status": "passed", "duration": 0.2, "status_code": 204},
            {"total": 1, "passed": 1, "failed": 0, "status_code": 204},
        ),
        (
            "ui_case",
            {
                "status": "passed",
                "total_steps": 3,
                "passed_steps": 2,
                "failed_steps": 1,
                "duration": 1.5,
            },
            {"total": 3, "passed": 2, "failed": 1},
        ),
        (
            "ui_suite",
            {
                "status": "failed",
                "total": 4,
                "passed": 3,
                "failed": 1,
                "duration": 5.0,
            },
            {"total": 4, "passed": 3, "failed": 1},
        ),
        (
            "performance",
            {
                "status": "passed",
                "total_requests": 20,
                "success_requests": 18,
                "fail_requests": 2,
                "duration": 4.0,
                "p95": 12.5,
                "rps": 5.0,
            },
            {"total": 20, "passed": 18, "failed": 2},
        ),
    ],
)
def test_pre_upgrade_job_log_is_normalized(
    db_session,
    job_type,
    payload,
    expected,
):
    job = ExecutionJob(
        job_type=job_type,
        status="succeeded" if payload["status"] == "passed" else "failed",
        config={},
        created_at=datetime(2026, 7, 1, 10, 0),
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.log",
            sequence=1,
            payload=json.dumps(payload),
        )
    )
    db_session.commit()

    metrics = get_job_metrics(db_session, job)

    for key, value in expected.items():
        assert metrics[key] == value


def test_normalized_run_uses_persisted_job_metrics(db_session):
    job = ExecutionJob(
        job_type="performance",
        status="succeeded",
        resource_id=None,
        result_summary="performance completed",
        config={
            RESULT_METRICS_CONFIG_KEY: {
                "total": 10,
                "passed": 9,
                "failed": 1,
                "error": 0,
                "skipped": 0,
                "duration": 2.0,
            }
        },
        created_at=datetime(2026, 7, 1, 10, 0),
    )
    db_session.add(job)
    db_session.commit()

    run = normalize_job_run(db_session, job, include_results=True)

    assert run["run_id"] == job.id
    assert run["source"] == "performance"
    assert run["total"] == 10
    assert run["passed"] == 9
    assert run["pass_rate"] == 90.0
    assert run["results"][0]["status"] == "passed"
