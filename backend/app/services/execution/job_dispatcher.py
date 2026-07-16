"""Dispatch execution jobs to Celery or an explicit local fallback."""
from __future__ import annotations

import logging
import os
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.execution_job import ExecutionJob
from app.services.execution.job_service import JobService
from app.tasks.celery_app import CELERY_AVAILABLE
from app.tasks.celery_app import app as celery_app
from app.tasks.job_task import run_execution_job

logger = logging.getLogger(__name__)

DispatchMode = Literal["celery", "local", "eager"]

_TASK_NAMES = {
    "api_case": "airetest.jobs.api",
    "ui_case": "airetest.jobs.ui",
    "ui_suite": "airetest.jobs.ui",
    "performance": "airetest.jobs.performance",
}


class JobDispatchError(RuntimeError):
    """Raised when a job cannot be submitted to any configured executor."""


@dataclass(frozen=True)
class DispatchResult:
    task_id: str
    queue: str
    mode: DispatchMode
    submitted: bool = True


@dataclass
class _LocalTask:
    cancel_event: threading.Event
    thread: threading.Thread


class JobDispatcher:
    """Queue router with Celery, eager, and local-thread execution modes."""

    _local_tasks: dict[str, _LocalTask] = {}
    _local_tasks_lock = threading.Lock()

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory

    @classmethod
    def from_session(
        cls,
        db: Session,
        *,
        settings: Settings | None = None,
    ) -> JobDispatcher:
        """Build fallback sessions against the same engine as the API session."""
        bind = db.get_bind()

        def session_factory() -> Session:
            return Session(bind=bind, autoflush=False, expire_on_commit=False)

        return cls(settings=settings, session_factory=session_factory)

    def dispatch(
        self,
        job: ExecutionJob,
        service: JobService,
    ) -> DispatchResult:
        """Persist dispatch metadata, then submit the job exactly once."""
        existing_task_id = service.get_celery_task_id(job)
        if existing_task_id:
            metadata = service.get_dispatch_metadata(job)
            return DispatchResult(
                task_id=existing_task_id,
                queue=str(metadata.get("queue") or self._queue_for(job.job_type)),
                mode=self._coerce_persisted_mode(metadata.get("mode")),
                submitted=False,
            )
        if job.status != "queued":
            raise JobDispatchError(
                f"Job '{job.id}' is in state '{job.status}' and cannot be dispatched"
            )

        task_id = str(uuid.uuid4())
        queue = self._queue_for(job.job_type)
        mode = self._select_mode()
        persisted = service.record_dispatch(
            job.id,
            task_id=task_id,
            queue=queue,
            mode=mode,
        )
        persisted_task_id = service.get_celery_task_id(persisted)
        if persisted_task_id != task_id:
            metadata = service.get_dispatch_metadata(persisted)
            if not persisted_task_id:
                raise JobDispatchError(
                    f"Job '{job.id}' left queued state before dispatch"
                )
            return DispatchResult(
                task_id=persisted_task_id,
                queue=str(metadata.get("queue") or queue),
                mode=self._coerce_persisted_mode(metadata.get("mode")),
                submitted=False,
            )

        try:
            self._submit(
                job_id=job.id,
                job_type=job.job_type,
                task_id=task_id,
                queue=queue,
                mode=mode,
                priority=job.priority,
                timeout_seconds=job.timeout_seconds,
            )
        except Exception as exc:
            fallback_mode = self._fallback_mode(exclude=mode)
            if fallback_mode is None:
                service.mark_dispatch_failed(job.id, str(exc))
                raise JobDispatchError(
                    f"Failed to dispatch job '{job.id}' using {mode}: {exc}"
                ) from exc

            logger.warning(
                "Job %s dispatch via %s failed; falling back to %s: %s",
                job.id,
                mode,
                fallback_mode,
                exc,
            )
            service.record_dispatch(
                job.id,
                task_id=task_id,
                queue=queue,
                mode=fallback_mode,
                replace=True,
            )
            try:
                self._submit(
                    job_id=job.id,
                    job_type=job.job_type,
                    task_id=task_id,
                    queue=queue,
                    mode=fallback_mode,
                    priority=job.priority,
                    timeout_seconds=job.timeout_seconds,
                )
            except Exception as fallback_exc:
                service.mark_dispatch_failed(job.id, str(fallback_exc))
                raise JobDispatchError(
                    f"Failed to dispatch job '{job.id}' using fallback "
                    f"{fallback_mode}: {fallback_exc}"
                ) from fallback_exc
            mode = fallback_mode

        service.db.expire_all()
        return DispatchResult(task_id=task_id, queue=queue, mode=mode)

    def revoke(
        self,
        task_id: str,
        *,
        mode: str | None,
        terminate: bool,
    ) -> bool:
        """Revoke a queued task and request termination for a running task."""
        if mode == "celery":
            if not CELERY_AVAILABLE or celery_app is None:
                raise JobDispatchError("Celery is unavailable; task cannot be revoked")
            celery_app.control.revoke(
                task_id,
                terminate=terminate,
                signal=self.settings.CELERY_TERMINATE_SIGNAL,
            )
            return True

        if mode == "local":
            with self._local_tasks_lock:
                local_task = self._local_tasks.get(task_id)
            if local_task is None:
                return False
            local_task.cancel_event.set()
            return True

        # Eager tasks have completed before control returns to the API.
        return mode == "eager"

    def _submit(
        self,
        *,
        job_id: str,
        job_type: str,
        task_id: str,
        queue: str,
        mode: DispatchMode,
        priority: int,
        timeout_seconds: int,
    ) -> None:
        if mode == "celery":
            self._submit_celery(
                job_id=job_id,
                job_type=job_type,
                task_id=task_id,
                queue=queue,
                priority=priority,
                timeout_seconds=timeout_seconds,
            )
            return
        if mode == "eager":
            run_execution_job(
                job_id,
                celery_task_id=task_id,
                session_factory=self.session_factory,
            )
            return
        self._submit_local(job_id=job_id, task_id=task_id)

    def _submit_celery(
        self,
        *,
        job_id: str,
        job_type: str,
        task_id: str,
        queue: str,
        priority: int,
        timeout_seconds: int,
    ) -> None:
        if not CELERY_AVAILABLE or celery_app is None:
            raise JobDispatchError("Celery is not installed")
        celery_app.send_task(
            _TASK_NAMES[job_type],
            args=[job_id],
            task_id=task_id,
            queue=queue,
            priority=priority,
            soft_time_limit=timeout_seconds,
            time_limit=timeout_seconds + 10,
        )

    def _submit_local(self, *, job_id: str, task_id: str) -> None:
        cancel_event = threading.Event()

        def target() -> None:
            try:
                if not cancel_event.is_set():
                    run_execution_job(
                        job_id,
                        celery_task_id=task_id,
                        session_factory=self.session_factory,
                    )
            except Exception:
                logger.exception("Local fallback execution failed for job %s", job_id)
            finally:
                with self._local_tasks_lock:
                    self._local_tasks.pop(task_id, None)

        thread = threading.Thread(
            target=target,
            name=f"job-{task_id[:8]}",
            daemon=True,
        )
        with self._local_tasks_lock:
            self._local_tasks[task_id] = _LocalTask(cancel_event, thread)
        thread.start()

    def _select_mode(self) -> DispatchMode:
        configured = str(self.settings.TASK_DISPATCH_MODE)
        if configured == "celery":
            return "celery"
        if configured == "local":
            return "local"
        if configured == "eager":
            return "eager"
        if self.settings.TASK_EAGER_IN_TESTS and os.getenv("PYTEST_CURRENT_TEST"):
            return "eager"
        if CELERY_AVAILABLE:
            return "celery"
        fallback = self._fallback_mode()
        if fallback is None:
            raise JobDispatchError(
                "Celery is unavailable and TASK_FALLBACK_MODE is disabled"
            )
        return fallback

    def _fallback_mode(
        self,
        *,
        exclude: DispatchMode | None = None,
    ) -> Literal["local", "eager"] | None:
        fallback = str(self.settings.TASK_FALLBACK_MODE)
        if fallback == "disabled" or fallback == exclude:
            return None
        if fallback == "eager":
            return "eager"
        return "local"

    def _queue_for(self, job_type: str) -> str:
        if job_type == "api_case":
            return str(self.settings.CELERY_API_QUEUE)
        if job_type in {"ui_case", "ui_suite"}:
            return str(self.settings.CELERY_UI_QUEUE)
        if job_type == "performance":
            return str(self.settings.CELERY_PERFORMANCE_QUEUE)
        raise JobDispatchError(f"Unsupported job type: {job_type}")

    @staticmethod
    def _coerce_persisted_mode(value: object) -> DispatchMode:
        if value == "celery":
            return "celery"
        if value == "eager":
            return "eager"
        return "local"
