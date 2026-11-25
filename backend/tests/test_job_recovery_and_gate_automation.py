"""P0/P1 minimal improvements: local job recovery and gate automation."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone

from app.models.execution_job import ExecutionAttempt, ExecutionJob
from app.models.project import Project
from app.models.quality_gate import QualityGate, QualityGateResult
from app.services.execution.job_service import (
    JobService,
    recover_interrupted_local_jobs,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def _session_factory(db: Session) -> Callable[[], Session]:
    bind = db.get_bind()
    return lambda: Session(bind=bind, autoflush=False, expire_on_commit=False)


def _local_job(
    db: Session,
    *,
    status: str,
    mode: str = "local",
) -> ExecutionJob:
    service = JobService(db)
    job = service.create_job(job_type="api_case")
    job.status = status
    job.config = {
        "_task_dispatch": {
            "celery_task_id": f"task-{job.id}",
            "queue": "airetest.api",
            "mode": mode,
        }
    }
    if status == "running":
        db.add(
            ExecutionAttempt(
                job_id=job.id,
                attempt_number=1,
                status="running",
                worker_id="old-worker",
                started_at=datetime.now(timezone.utc),
            )
        )
    db.commit()
    return job


def test_recover_interrupted_local_jobs_marks_stale_jobs_failed(
    db_session,
):
    running = _local_job(db_session, status="running")
    queued = _local_job(db_session, status="queued")
    celery_running = _local_job(
        db_session,
        status="running",
        mode="celery",
    )
    service = JobService(db_session)
    succeeded = service.create_job(job_type="api_case")
    succeeded.status = "succeeded"
    db_session.commit()

    stats = recover_interrupted_local_jobs(_session_factory(db_session))

    assert stats == {
        "recovered": 2,
        "queued": 1,
        "running": 1,
    }

    db_session.expire_all()
    recovered_running = db_session.get(ExecutionJob, running.id)
    recovered_queued = db_session.get(ExecutionJob, queued.id)
    untouched_celery = db_session.get(ExecutionJob, celery_running.id)
    untouched_succeeded = db_session.get(ExecutionJob, succeeded.id)

    assert recovered_running.status == "failed"
    assert recovered_running.error_code == "process_restart"
    assert recovered_running.finished_at is not None
    assert recovered_queued.status == "failed"
    assert recovered_queued.error_code == "process_restart"
    assert untouched_celery.status == "running"
    assert untouched_succeeded.status == "succeeded"

    running_attempt = (
        db_session.execute(
            select(ExecutionAttempt).where(
                ExecutionAttempt.job_id == running.id
            )
        )
        .scalars()
        .one()
    )
    assert running_attempt.status == "failed"
    assert running_attempt.error_code == "process_restart"

    events = JobService(db_session).get_events(running.id)
    recovery_event = next(
        event for event in events if event.event_type == "job.failed"
    )
    payload = json.loads(recovery_event.payload)
    assert payload["error_code"] == "process_restart"
    assert payload["previous_status"] == "running"
    assert payload["dispatch_mode"] == "local"


def test_quality_gate_is_evaluated_after_terminal_job(
    db_session,
    monkeypatch,
):
    project = Project(
        id="project-auto-gate",
        name="自动门禁项目",
        code="auto-gate",
    )
    passing_gate = QualityGate(
        id="gate-passing",
        name="通过门禁",
        project_id=project.id,
        rules=json.dumps(
            [
                {
                    "metric": "pass_rate",
                    "op": ">=",
                    "value": 0.9,
                }
            ]
        ),
        mode="block",
        is_active=True,
    )
    failing_gate = QualityGate(
        id="gate-failing",
        name="失败门禁",
        project_id=project.id,
        rules=json.dumps(
            [
                {
                    "metric": "pass_rate",
                    "op": ">=",
                    "threshold": 1.1,
                }
            ]
        ),
        mode="warn",
        is_active=True,
    )
    db_session.add_all([project, passing_gate, failing_gate])
    db_session.commit()

    service = JobService(db_session)
    job = service.create_job(
        job_type="api_case",
        project_id=project.id,
    )

    def fake_run(_service, running_job):
        return {
            "status": "succeeded",
            "summary": f"{running_job.id} completed",
            "metrics": {
                "total": 4,
                "passed": 4,
                "failed": 0,
                "error": 0,
                "skipped": 0,
                "duration": 0.25,
                "results": [],
            },
        }

    monkeypatch.setattr(JobService, "_run", fake_run)
    completed = service.execute_job(job.id, worker_id="gate-worker")

    assert completed.status == "succeeded"
    results = list(
        db_session.execute(
            select(QualityGateResult).where(
                QualityGateResult.run_id == job.id
            )
        )
        .scalars()
        .all()
    )
    assert len(results) == 2
    by_gate = {result.gate_id: result for result in results}
    assert by_gate["gate-passing"].passed is True
    assert by_gate["gate-failing"].passed is False

    passing_rule_results = json.loads(by_gate["gate-passing"].results)
    assert passing_rule_results[0]["metric"] == "pass_rate"
    assert passing_rule_results[0]["threshold"] == 0.9
    assert passing_rule_results[0]["actual"] == 1.0
    assert by_gate["gate-passing"].triggered_by.startswith("job:")

    events = service.get_events(job.id)
    gate_event = next(
        event
        for event in events
        if event.event_type == "job.quality_gates.evaluated"
    )
    gate_payload = json.loads(gate_event.payload)
    assert {item["gate_id"] for item in gate_payload["results"]} == {
        "gate-passing",
        "gate-failing",
    }

    gate_failure_event = next(
        event
        for event in events
        if event.event_type == "job.quality_gate.failed"
    )
    gate_failure_payload = json.loads(gate_failure_event.payload)
    assert {item["gate_id"] for item in gate_failure_payload["results"]} == {
        "gate-failing"
    }

    terminal = next(
        event for event in events if event.event_type == "job.completed"
    )
    terminal_payload = json.loads(terminal.payload)
    assert len(terminal_payload["quality_gates"]) == 2
