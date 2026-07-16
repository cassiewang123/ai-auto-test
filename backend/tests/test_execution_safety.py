"""Execution safety boundaries for production, scripts, and local runners."""
from __future__ import annotations

import multiprocessing
import threading
import time
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.api.v1 import execution as execution_api
from app.config import Settings
from app.runners.base import ExecutionJobSpec, RunnerHandle, RunnerStatus
from app.runners.local_process import LocalProcessRunner
from app.runners.script_process import run_script_in_subprocess

_PRODUCTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
_SAFE_PRODUCTION_SETTINGS = {
    "_env_file": None,
    "ENVIRONMENT": "production",
    "SECRET_KEY": "production-jwt-secret",
    "SECRET_ENCRYPTION_KEY": _PRODUCTION_KEY,
    "ALLOW_SYNC_EXECUTION": False,
    "TASK_DISPATCH_MODE": "celery",
    "TASK_FALLBACK_MODE": "disabled",
}


def test_default_settings_use_lightweight_local_mode(monkeypatch) -> None:
    for name in (
        "DATABASE_URL",
        "TASK_DISPATCH_MODE",
        "TASK_FALLBACK_MODE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.DATABASE_URL == "sqlite:///./airetest-lite.db"
    assert settings.TASK_DISPATCH_MODE == "local"
    assert settings.TASK_FALLBACK_MODE == "disabled"
    assert settings.ARTIFACT_ROOT.as_posix() == ".uploads"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"ALLOW_SYNC_EXECUTION": True}, "ALLOW_SYNC_EXECUTION=false"),
        ({"SECRET_KEY": "dev-secret-change-in-production"}, "explicit SECRET_KEY"),
        ({"TASK_DISPATCH_MODE": "local"}, "TASK_DISPATCH_MODE"),
        ({"TASK_DISPATCH_MODE": "eager"}, "TASK_DISPATCH_MODE"),
        ({"TASK_FALLBACK_MODE": "local"}, "TASK_FALLBACK_MODE=disabled"),
        ({"TASK_FALLBACK_MODE": "eager"}, "TASK_FALLBACK_MODE=disabled"),
    ],
)
def test_production_rejects_unsafe_execution_settings(
    override: dict[str, object],
    message: str,
) -> None:
    values = {**_SAFE_PRODUCTION_SETTINGS, **override}
    with pytest.raises(PydanticValidationError, match=message):
        Settings(**values)


def test_production_accepts_only_async_worker_execution() -> None:
    settings = Settings(**_SAFE_PRODUCTION_SETTINGS)

    assert settings.ALLOW_SYNC_EXECUTION is False
    assert settings.TASK_DISPATCH_MODE == "celery"
    assert settings.TASK_FALLBACK_MODE == "disabled"


@pytest.mark.parametrize(
    ("path", "request_kwargs"),
    [
        (
            "/api/v1/execution/run",
            {"json": {"method": "GET", "url": "https://example.com"}},
        ),
        (
            "/api/v1/execution/run-multipart",
            {"data": {"method": "GET", "url": "https://example.com"}},
        ),
        (
            "/api/v1/execution/run/missing-case",
            {},
        ),
    ],
)
def test_sync_execution_endpoints_reject_production_even_if_flag_is_true(
    client,
    monkeypatch,
    path: str,
    request_kwargs: dict[str, object],
) -> None:
    monkeypatch.setattr(
        execution_api,
        "get_settings",
        lambda: SimpleNamespace(
            ENVIRONMENT="production",
            ALLOW_SYNC_EXECUTION=True,
            SCRIPT_EXECUTION_TIMEOUT=1,
        ),
    )

    response = client.post(path, **request_kwargs)

    assert response.status_code == 403
    assert "/api/v1/jobs" in response.text


def test_script_runs_in_isolated_process_and_returns_variable_changes() -> None:
    context = {"variables": {"count": 1}}

    result = run_script_in_subprocess(
        "variables['count'] = variables['count'] + 1\nprint('done')",
        context,
        timeout_seconds=5,
    )

    assert result["success"] is True
    assert result["variables"]["count"] == 2
    assert result["output"] == "done\n"
    assert context["variables"]["count"] == 1


def test_script_timeout_terminates_child_process() -> None:
    started_at = time.monotonic()

    result = run_script_in_subprocess(
        "while True:\n    pass",
        {"variables": {}},
        timeout_seconds=0.2,
    )

    assert result["success"] is False
    assert "timed out" in result["error"]
    assert time.monotonic() - started_at < 3
    assert all(
        child.name != "airetest-script"
        for child in multiprocessing.active_children()
    )


class _StubLocalRunner(LocalProcessRunner):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def _execute(self, job: ExecutionJobSpec) -> dict:
        return self.callback(job)


def test_local_runner_maps_failed_result_instead_of_forcing_success() -> None:
    runner = _StubLocalRunner(
        lambda job: {"status": "failed", "error": f"{job.job_id} failed"}
    )

    handle = runner.submit(
        ExecutionJobSpec(job_id="failed-job", job_type="api_case")
    )

    assert handle.status == RunnerStatus.FAILED
    assert handle.error == "failed-job failed"


def test_local_runner_rejects_missing_result_status() -> None:
    runner = _StubLocalRunner(lambda job: {"job_id": job.job_id})

    handle = runner.submit(
        ExecutionJobSpec(job_id="missing-status", job_type="api_case")
    )

    assert handle.status == RunnerStatus.FAILED
    assert "unsupported status" in (handle.error or "")


def test_local_runner_timeout_is_not_overwritten_by_late_success() -> None:
    release = threading.Event()
    runner = _StubLocalRunner(
        lambda job: (
            release.wait(timeout=1)
            and {"status": "succeeded", "job_id": job.job_id}
        )
        or {"status": "succeeded", "job_id": job.job_id}
    )

    handle = runner.submit(
        ExecutionJobSpec(
            job_id="timeout-job",
            job_type="api_case",
            timeout_seconds=0.05,
        )
    )
    assert handle.status == RunnerStatus.TIMED_OUT

    release.set()
    time.sleep(0.05)

    assert handle.status == RunnerStatus.TIMED_OUT
    assert "timed out" in (handle.error or "")


def test_local_runner_cancel_discards_late_success() -> None:
    started = threading.Event()
    release = threading.Event()

    def execute(job: ExecutionJobSpec) -> dict:
        started.set()
        release.wait(timeout=1)
        return {"status": "succeeded", "job_id": job.job_id}

    runner = _StubLocalRunner(execute)
    submitted: dict[str, RunnerHandle] = {}

    submit_thread = threading.Thread(
        target=lambda: submitted.setdefault(
            "handle",
            runner.submit(
                ExecutionJobSpec(
                    job_id="cancel-job",
                    job_type="api_case",
                    timeout_seconds=2,
                )
            ),
        )
    )
    submit_thread.start()
    assert started.wait(timeout=1)

    cancellation_handle = RunnerHandle(job_id="cancel-job")
    runner.cancel(cancellation_handle)
    submit_thread.join(timeout=1)

    assert submitted["handle"].status == RunnerStatus.CANCELLED
    assert cancellation_handle.status == RunnerStatus.CANCELLED

    release.set()
    time.sleep(0.05)

    assert submitted["handle"].status == RunnerStatus.CANCELLED


def test_local_runner_does_not_cancel_completed_handle() -> None:
    runner = _StubLocalRunner(
        lambda job: {"status": "succeeded", "job_id": job.job_id}
    )
    handle = runner.submit(
        ExecutionJobSpec(job_id="completed-job", job_type="api_case")
    )

    runner.cancel(handle)

    assert handle.status == RunnerStatus.SUCCEEDED


def test_unconfigured_local_runner_fails_instead_of_returning_placeholder_success() -> None:
    handle = LocalProcessRunner().submit(
        ExecutionJobSpec(job_id="unconfigured", job_type="api_case")
    )

    assert handle.status == RunnerStatus.FAILED
    assert "no configured API case executor" in (handle.error or "")
