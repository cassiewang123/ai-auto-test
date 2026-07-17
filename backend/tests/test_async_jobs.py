"""First-stage asynchronous execution job tests without Redis."""
from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.execution_job import ExecutionAttempt, ExecutionJob
from app.models.job_artifact import JobArtifact
from app.models.performance_result import PerformanceResult
from app.models.performance_test import PerformanceTest
from app.models.ui_test_case import UiTestCase
from app.models.ui_test_record import UiTestRecord
from app.models.ui_test_suite import UiTestSuite, UiTestSuiteRun
from app.services.execution import job_dispatcher as dispatcher_module
from app.services.execution.job_dispatcher import JobDispatcher
from app.services.execution.job_reporting import RESULT_METRICS_CONFIG_KEY
from app.services.execution.job_service import JobService
from app.tasks.job_task import run_execution_job


def _celery_settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite://",
        TASK_DISPATCH_MODE="celery",
        TASK_FALLBACK_MODE="disabled",
        TASK_EAGER_IN_TESTS=False,
    )


def _session_factory(db: Session) -> Callable[[], Session]:
    bind = db.get_bind()
    return lambda: Session(bind=bind, autoflush=False, expire_on_commit=False)


def test_post_job_dispatches_without_inline_execution(
    client,
    db_session,
    monkeypatch,
):
    submitted: list[dict] = []

    def select_celery(self):
        return "celery"

    def submit_celery(self, **kwargs):
        submitted.append(kwargs)

    monkeypatch.setattr(
        JobDispatcher,
        "_select_mode",
        select_celery,
    )
    monkeypatch.setattr(
        JobDispatcher,
        "_submit_celery",
        submit_celery,
    )

    response = client.post(
        "/api/v1/jobs",
        json={"job_type": "api_case"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "queued"
    assert payload["celery_task_id"]
    assert payload["dispatch_queue"] == "airetest.api"
    assert len(submitted) == 1
    assert submitted[0]["job_id"] == payload["id"]
    assert (
        db_session.query(ExecutionAttempt)
        .filter(ExecutionAttempt.job_id == payload["id"])
        .count()
        == 0
    )


@pytest.mark.parametrize(
    ("job_type", "expected_queue", "expected_task_name"),
    [
        ("api_case", "airetest.api", "airetest.jobs.api"),
        ("ui_case", "airetest.ui", "airetest.jobs.ui"),
        ("ui_suite", "airetest.ui", "airetest.jobs.ui"),
        (
            "performance",
            "airetest.performance",
            "airetest.jobs.performance",
        ),
    ],
)
def test_job_types_route_to_dedicated_celery_queues(
    db_session,
    monkeypatch,
    job_type,
    expected_queue,
    expected_task_name,
):
    sent: list[dict] = []

    def send_task(self, name, **kwargs):
        sent.append({"name": name, **kwargs})

    fake_app = type(
        "FakeCelery",
        (),
        {"send_task": send_task},
    )()
    monkeypatch.setattr(dispatcher_module, "CELERY_AVAILABLE", True)
    monkeypatch.setattr(dispatcher_module, "celery_app", fake_app)

    service = JobService(db_session)
    job = service.create_job(job_type=job_type)
    result = JobDispatcher(
        settings=_celery_settings(),
        session_factory=_session_factory(db_session),
    ).dispatch(job, service)

    assert result.queue == expected_queue
    assert result.mode == "celery"
    assert sent[0]["name"] == expected_task_name
    assert sent[0]["queue"] == expected_queue
    db_session.expire_all()
    persisted = db_session.get(ExecutionJob, job.id)
    assert JobService.get_celery_task_id(persisted) == result.task_id


def test_idempotency_key_does_not_submit_the_same_job_twice(
    client,
    monkeypatch,
):
    submitted: list[str] = []

    def select_celery(self):
        return "celery"

    def submit_celery(self, **kwargs):
        submitted.append(kwargs["job_id"])

    monkeypatch.setattr(
        JobDispatcher,
        "_select_mode",
        select_celery,
    )
    monkeypatch.setattr(
        JobDispatcher,
        "_submit_celery",
        submit_celery,
    )

    request = {
        "job_type": "ui_case",
        "idempotency_key": "same-request",
    }
    first = client.post("/api/v1/jobs", json=request)
    second = client.post("/api/v1/jobs", json=request)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert first.json()["data"]["celery_task_id"] == second.json()["data"]["celery_task_id"]
    assert len(submitted) == 1


def test_unavailable_celery_uses_configured_eager_fallback(
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(dispatcher_module, "CELERY_AVAILABLE", False)
    monkeypatch.setattr(dispatcher_module, "celery_app", None)
    monkeypatch.setattr(
        "app.services.ui.artifact_service.get_artifact_root",
        lambda: tmp_path,
    )
    case = UiTestCase(
        title="eager UI case",
        url="https://example.com",
        browser_type="chrome",
        steps=[{"action": "navigate"}],
    )
    db_session.add(case)
    db_session.commit()

    def fake_execute_ui_case(**_kwargs):
        return (
            {
                "status": "passed",
                "total_steps": 1,
                "passed_steps": 1,
                "failed_steps": 0,
                "error": None,
                "steps": [{"step": 1, "status": "passed"}],
                "screenshots": [],
                "trace_path": None,
            },
            [{"attempt": 1, "status": "passed", "duration": 0.01, "error": None}],
            1,
        )

    monkeypatch.setattr(
        "app.services.ui.execution_service.execute_ui_case",
        fake_execute_ui_case,
    )
    settings = Settings(
        DATABASE_URL="sqlite://",
        TASK_DISPATCH_MODE="celery",
        TASK_FALLBACK_MODE="eager",
        TASK_EAGER_IN_TESTS=False,
    )

    service = JobService(db_session)
    job = service.create_job(job_type="ui_case", resource_id=case.id)
    result = JobDispatcher(
        settings=settings,
        session_factory=_session_factory(db_session),
    ).dispatch(job, service)

    db_session.expire_all()
    persisted = db_session.get(ExecutionJob, job.id)
    metadata = JobService.get_dispatch_metadata(persisted)
    assert result.mode == "eager"
    assert persisted.status == "succeeded"
    assert persisted.attempt_count == 1
    assert metadata["mode"] == "eager"
    assert metadata["celery_task_id"] == result.task_id


@pytest.mark.parametrize(
    ("status", "expected_terminate"),
    [("queued", False), ("running", True)],
)
def test_cancel_revokes_queued_and_running_tasks(
    client,
    db_session,
    monkeypatch,
    status,
    expected_terminate,
):
    def select_celery(self):
        return "celery"

    def submit_celery(self, **kwargs):
        return None

    monkeypatch.setattr(
        JobDispatcher,
        "_select_mode",
        select_celery,
    )
    monkeypatch.setattr(
        JobDispatcher,
        "_submit_celery",
        submit_celery,
    )
    revoked: list[dict] = []

    def revoke(self, task_id, **kwargs):
        revoked.append({"task_id": task_id, **kwargs})
        return True

    monkeypatch.setattr(
        JobDispatcher,
        "revoke",
        revoke,
    )

    created = client.post(
        "/api/v1/jobs",
        json={"job_type": "performance"},
    ).json()["data"]
    job = db_session.get(ExecutionJob, created["id"])
    job.status = status
    db_session.commit()

    response = client.post(f"/api/v1/jobs/{job.id}/cancel")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "cancelled"
    assert revoked == [
        {
            "task_id": created["celery_task_id"],
            "mode": "celery",
            "terminate": expected_terminate,
        }
    ]


def test_cancelled_job_is_not_restarted_by_late_delivery(db_session):
    service = JobService(db_session)
    job = service.create_job(job_type="ui_case")
    service.record_dispatch(
        job.id,
        task_id="late-task",
        queue="airetest.ui",
        mode="celery",
    )
    service.cancel_job(job.id)

    result = run_execution_job(
        job.id,
        celery_task_id="late-task",
        session_factory=_session_factory(db_session),
    )

    db_session.expire_all()
    persisted = db_session.get(ExecutionJob, job.id)
    assert result["status"] == "cancelled"
    assert persisted.status == "cancelled"
    assert persisted.attempt_count == 0


def test_running_job_completion_does_not_overwrite_cancellation(
    db_session,
    monkeypatch,
):
    service = JobService(db_session)
    job = service.create_job(job_type="ui_case")
    session_factory = _session_factory(db_session)

    def cancel_during_run(self, running_job):
        other = session_factory()
        try:
            JobService(other).cancel_job(running_job.id)
        finally:
            other.close()
        return {"status": "succeeded", "summary": "late success"}

    monkeypatch.setattr(JobService, "_run", cancel_during_run)
    completed = service.execute_job(job.id, worker_id="test-worker")

    assert completed.status == "cancelled"
    attempt = (
        db_session.query(ExecutionAttempt)
        .filter(ExecutionAttempt.job_id == job.id)
        .one()
    )
    assert attempt.status == "cancelled"


def test_ui_case_job_uses_real_service_and_returns_artifacts(
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.ui.artifact_service.get_artifact_root",
        lambda: tmp_path,
    )
    case = UiTestCase(
        title="checkout",
        url="https://example.com/checkout",
        browser_type="chrome",
        steps=[{"action": "navigate"}],
        retry_count=1,
        retry_interval=0,
    )
    db_session.add(case)
    db_session.commit()
    calls: list[dict] = []
    screenshot = base64.b64encode(b"fake-png").decode()

    def fake_execute_ui_case(**kwargs):
        calls.append(kwargs)
        artifact_dir = Path(kwargs["artifact_dir"])
        artifact_dir.mkdir(parents=True, exist_ok=True)
        trace_path = artifact_dir / f"trace_{kwargs['job_id']}.zip"
        trace_path.write_bytes(b"fake-trace")
        return (
            {
                "status": "passed",
                "total_steps": 1,
                "passed_steps": 1,
                "failed_steps": 0,
                "error": None,
                "steps": [{"step": 1, "status": "passed"}],
                "screenshots": [screenshot],
                "trace_path": str(trace_path),
            },
            [{"attempt": 1, "status": "passed", "duration": 0.01, "error": None}],
            1,
        )

    monkeypatch.setattr(
        "app.services.ui.execution_service.execute_ui_case",
        fake_execute_ui_case,
    )
    service = JobService(db_session)
    job = service.create_job(job_type="ui_case", resource_id=case.id)

    payload = run_execution_job(
        job.id,
        celery_task_id="ui-task",
        session_factory=_session_factory(db_session),
    )

    assert payload["status"] == "succeeded"
    assert payload["summary"].startswith("UI 用例执行通过")
    assert payload["error"] is None
    assert {item["artifact_type"] for item in payload["artifacts"]} == {
        "screenshot",
        "trace",
    }
    assert calls[0]["url"] == case.url
    assert calls[0]["retry_count"] == 1
    assert calls[0]["job_id"] == job.id
    db_session.expire_all()
    record = db_session.query(UiTestRecord).filter_by(case_id=case.id).one()
    assert record.status == "passed"
    assert record.triggered_by == f"job:{job.id}"
    assert db_session.query(JobArtifact).filter_by(job_id=job.id).count() == 2
    persisted = db_session.get(ExecutionJob, job.id)
    metrics = persisted.config[RESULT_METRICS_CONFIG_KEY]
    assert (metrics["total"], metrics["passed"], metrics["failed"]) == (1, 1, 0)


def test_ui_suite_job_reuses_suite_execution_and_maps_case_failure(
    db_session,
    monkeypatch,
    tmp_path,
):
    from app.api.v1 import ui_test_suites as suite_module

    monkeypatch.setattr(
        "app.services.ui.artifact_service.get_artifact_root",
        lambda: tmp_path,
    )
    cases = [
        UiTestCase(
            title="first",
            url="https://example.com/first",
            browser_type="chrome",
            steps=[{"action": "navigate"}],
        ),
        UiTestCase(
            title="second",
            url="https://example.com/second",
            browser_type="chrome",
            steps=[{"action": "navigate"}],
        ),
    ]
    db_session.add_all(cases)
    db_session.flush()
    suite = UiTestSuite(
        name="smoke",
        case_ids=[case.id for case in cases],
        execution_mode="sequential",
        retry_enabled=True,
    )
    db_session.add(suite)
    db_session.commit()
    executed: list[str] = []
    screenshot = base64.b64encode(b"suite-png").decode()

    def fake_execute_single_case(
        case,
        _steps,
        retry_count=0,
        retry_interval=2.0,
    ):
        executed.append(case.id)
        passed = case.id == cases[0].id
        return {
            "case_id": case.id,
            "case_title": case.title,
            "project_id": case.project_id,
            "url": case.url,
            "browser_type": case.browser_type,
            "status": "passed" if passed else "failed",
            "total_steps": 1,
            "passed_steps": 1 if passed else 0,
            "failed_steps": 0 if passed else 1,
            "duration": 0.01,
            "error": None if passed else "assertion failed",
            "step_results": [],
            "screenshots": [screenshot],
            "started_at": datetime.now(),
            "retry_attempts": [
                {
                    "attempt": 1,
                    "status": "passed" if passed else "failed",
                    "duration": 0.01,
                    "error": None if passed else "assertion failed",
                }
            ],
            "final_attempt": 1,
        }

    monkeypatch.setattr(
        suite_module,
        "_execute_single_case",
        fake_execute_single_case,
    )
    service = JobService(db_session)
    job = service.create_job(job_type="ui_suite", resource_id=suite.id)

    completed = service.execute_job(job.id, worker_id="suite-worker")

    assert completed.status == "failed"
    assert completed.error_code == "ui_suite_failed"
    assert executed == [case.id for case in cases]
    suite_run = db_session.query(UiTestSuiteRun).filter_by(suite_id=suite.id).one()
    assert (suite_run.passed, suite_run.failed) == (1, 1)
    assert len(suite_run.record_ids) == 2
    assert db_session.query(UiTestRecord).count() == 2
    artifact_types = {
        row.artifact_type
        for row in db_session.query(JobArtifact).filter_by(job_id=job.id)
    }
    assert artifact_types == {"screenshot", "report"}
    metrics = completed.config[RESULT_METRICS_CONFIG_KEY]
    assert (metrics["total"], metrics["passed"], metrics["failed"]) == (2, 1, 1)
    assert len(metrics["results"]) == 2


def test_performance_job_uses_perf_runner_and_persists_report(
    db_session,
    monkeypatch,
    tmp_path,
):
    from app.services import perf_realtime, perf_runner

    monkeypatch.setattr(
        "app.services.ui.artifact_service.get_artifact_root",
        lambda: tmp_path,
    )
    test = PerformanceTest(
        name="baseline",
        case_ids=["api-case"],
        config={"users": 1, "duration": 1},
    )
    db_session.add(test)
    db_session.commit()
    called: list[tuple[str, str]] = []

    def fake_execute_performance_test(test_id: str, run_id: str | None = None):
        assert run_id is not None
        called.append((test_id, run_id))
        db_session.add(
            PerformanceResult(
                test_id=test_id,
                run_id=run_id,
                total_requests=10,
                success_requests=10,
                fail_requests=0,
                avg_response_time=20,
                min_response_time=10,
                max_response_time=30,
                p50=18,
                p90=24,
                p95=26,
                p99=29,
                rps=5,
                error_rate=0,
                duration=2,
                sla_status="passed",
                sla_details={},
                mode="steady",
            )
        )
        db_session.commit()
        return run_id

    monkeypatch.setattr(
        perf_runner,
        "execute_performance_test",
        fake_execute_performance_test,
    )
    monkeypatch.setattr(
        perf_realtime,
        "get",
        lambda test_id: {
            "test_id": test_id,
            "run_id": called[-1][1],
            "status": "completed",
            "error": None,
        },
    )
    service = JobService(db_session)
    job = service.create_job(job_type="performance", resource_id=test.id)

    completed = service.execute_job(job.id, worker_id="perf-worker")

    assert completed.status == "succeeded"
    assert called == [(test.id, job.id)]
    artifact = db_session.query(JobArtifact).filter_by(job_id=job.id).one()
    assert artifact.artifact_type == "report"
    assert artifact.filename == f"performance_{job.id}.json"
    metrics = completed.config[RESULT_METRICS_CONFIG_KEY]
    assert (metrics["total"], metrics["passed"], metrics["failed"]) == (10, 10, 0)
    assert metrics["p95"] == 26


def test_timeout_is_normalized_in_job_task_result(db_session, monkeypatch):
    service = JobService(db_session)
    job = service.create_job(job_type="ui_case")

    def raise_timeout(self, running_job):
        raise TimeoutError(f"{running_job.id} timed out")

    monkeypatch.setattr(JobService, "_run", raise_timeout)
    payload = run_execution_job(
        job.id,
        celery_task_id="timeout-task",
        session_factory=_session_factory(db_session),
    )

    assert payload["status"] == "timed_out"
    assert payload["summary"] == "任务执行超时"
    assert payload["error"]["code"] == "timeout"
    assert payload["artifacts"] == []
    attempt = (
        db_session.query(ExecutionAttempt)
        .filter(ExecutionAttempt.job_id == job.id)
        .one()
    )
    assert attempt.status == "timed_out"
