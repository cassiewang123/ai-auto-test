"""Development-only local runner with honest cancellation and timeout states."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.runners.base import (
    ExecutionArtifacts,
    ExecutionJobSpec,
    ExecutionRunner,
    RunnerHandle,
    RunnerStatus,
)

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {
    RunnerStatus.SUCCEEDED,
    RunnerStatus.FAILED,
    RunnerStatus.TIMED_OUT,
    RunnerStatus.CANCELLED,
}


@dataclass
class _LocalTask:
    handle: RunnerHandle
    cancel_event: threading.Event
    state_event: threading.Event
    thread: threading.Thread | None = None


class LocalProcessRunner(ExecutionRunner):
    """Run development fallback work locally without inventing success states.

    The compatibility interface remains synchronous, but the work itself runs in
    a daemon thread so timeout and cross-thread cancellation can return promptly.
    Local work cannot be forcefully terminated; cancellation and timeout discard
    any later result and production configuration rejects this runner mode.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, _LocalTask] = {}
        self._lock = threading.Lock()

    def submit(self, job: ExecutionJobSpec) -> RunnerHandle:
        handle = RunnerHandle(
            job_id=job.job_id,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
        )
        task = _LocalTask(
            handle=handle,
            cancel_event=threading.Event(),
            state_event=threading.Event(),
        )
        worker = threading.Thread(
            target=self._run_task,
            args=(job, task),
            name=f"local-runner-{job.job_id}",
            daemon=True,
        )
        task.thread = worker

        with self._lock:
            if job.job_id in self._tasks:
                handle.status = RunnerStatus.FAILED
                handle.error = f"Job '{job.job_id}' is already running locally"
                handle.finished_at = datetime.now()
                return handle
            self._tasks[job.job_id] = task

        try:
            worker.start()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._tasks.pop(job.job_id, None)
            handle.status = RunnerStatus.FAILED
            handle.error = f"Local worker failed to start: {type(exc).__name__}: {exc}"
            handle.finished_at = datetime.now()
            return handle

        completed = task.state_event.wait(timeout=max(float(job.timeout_seconds), 0.0))
        if not completed:
            with self._lock:
                if handle.status == RunnerStatus.RUNNING:
                    task.cancel_event.set()
                    handle.status = RunnerStatus.TIMED_OUT
                    handle.error = (
                        f"Local execution timed out after {job.timeout_seconds} seconds; "
                        "any later result will be discarded"
                    )
                    handle.finished_at = datetime.now()
        return handle

    def _run_task(self, job: ExecutionJobSpec, task: _LocalTask) -> None:
        result: dict[str, Any] | None = None
        error: Exception | None = None
        try:
            if not task.cancel_event.is_set():
                result = self._execute(job)
        except Exception as exc:  # noqa: BLE001
            error = exc
            logger.exception("Job %s failed", job.job_id)
        finally:
            with self._lock:
                handle = task.handle
                if handle.status not in {
                    RunnerStatus.CANCELLED,
                    RunnerStatus.TIMED_OUT,
                }:
                    if task.cancel_event.is_set():
                        handle.status = RunnerStatus.CANCELLED
                        handle.error = "Local execution was cancelled"
                    elif error is not None:
                        handle.status = RunnerStatus.FAILED
                        handle.error = str(error)
                    else:
                        self._apply_result(handle, result)
                    handle.finished_at = datetime.now()
                self._tasks.pop(job.job_id, None)
                task.state_event.set()

    @staticmethod
    def _apply_result(
        handle: RunnerHandle,
        result: dict[str, Any] | None,
    ) -> None:
        handle.result = result
        if not isinstance(result, dict):
            handle.status = RunnerStatus.FAILED
            handle.error = "Local execution returned no result"
            return

        raw_status = str((result or {}).get("status", "")).strip().lower()
        status_map = {
            "success": RunnerStatus.SUCCEEDED,
            "succeeded": RunnerStatus.SUCCEEDED,
            "passed": RunnerStatus.SUCCEEDED,
            "failed": RunnerStatus.FAILED,
            "failure": RunnerStatus.FAILED,
            "error": RunnerStatus.FAILED,
            "timed_out": RunnerStatus.TIMED_OUT,
            "timeout": RunnerStatus.TIMED_OUT,
            "cancelled": RunnerStatus.CANCELLED,
            "canceled": RunnerStatus.CANCELLED,
        }
        handle.status = status_map.get(raw_status, RunnerStatus.FAILED)
        if handle.status != RunnerStatus.SUCCEEDED:
            handle.error = str(
                (result or {}).get("error")
                or (result or {}).get("message")
                or f"Local execution returned unsupported status '{raw_status}'"
            )

    def _execute(self, job: ExecutionJobSpec) -> dict[str, Any]:
        """Dispatch to a concrete local implementation."""
        if job.job_type == "api_case":
            return self._execute_api_case(job)
        if job.job_type == "ui_case":
            return self._execute_ui_case(job)
        if job.job_type == "performance":
            return self._execute_performance(job)
        raise ValueError(f"Unknown job type: {job.job_type}")

    def _execute_api_case(self, job: ExecutionJobSpec) -> dict[str, Any]:
        raise NotImplementedError(
            "LocalProcessRunner has no configured API case executor"
        )

    def _execute_ui_case(self, job: ExecutionJobSpec) -> dict[str, Any]:
        raise NotImplementedError(
            "LocalProcessRunner has no configured UI case executor"
        )

    def _execute_performance(self, job: ExecutionJobSpec) -> dict[str, Any]:
        raise NotImplementedError(
            "LocalProcessRunner has no configured performance executor"
        )

    def cancel(self, handle: RunnerHandle) -> None:
        with self._lock:
            task = self._tasks.get(handle.job_id)
            if task is None:
                return

            canonical = task.handle
            if canonical.status in _TERMINAL_STATUSES:
                handle.status = canonical.status
                handle.result = canonical.result
                handle.error = canonical.error
                handle.started_at = canonical.started_at
                handle.finished_at = canonical.finished_at
                return

            task.cancel_event.set()
            canonical.status = RunnerStatus.CANCELLED
            canonical.error = (
                "Local cancellation requested; any later result will be discarded"
            )
            canonical.finished_at = datetime.now()
            task.state_event.set()
            handle.status = canonical.status
            handle.error = canonical.error
            handle.started_at = canonical.started_at
            handle.finished_at = canonical.finished_at

    def status(self, handle: RunnerHandle) -> RunnerStatus:
        with self._lock:
            task = self._tasks.get(handle.job_id)
            if task is not None:
                return task.handle.status
        return handle.status

    def collect(self, handle: RunnerHandle) -> ExecutionArtifacts:
        return ExecutionArtifacts()
