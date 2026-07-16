"""Shared execution entry point for Celery and local fallback tasks."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

ExecutionTaskResult = dict[str, Any]


def run_execution_job(
    job_id: str,
    *,
    celery_task_id: str | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> ExecutionTaskResult:
    """Execute one job with a session owned by this task invocation."""
    if session_factory is None:
        from app.database import SessionLocal

        session_factory = SessionLocal

    db = session_factory()
    try:
        from app.models.job_artifact import JobArtifact
        from app.services.execution.job_service import JobService

        worker_id = f"task-{celery_task_id}" if celery_task_id else None
        job = JobService(db).execute_job(job_id, worker_id=worker_id)
        artifacts = list(
            db.execute(
                select(JobArtifact)
                .where(JobArtifact.job_id == job.id)
                .order_by(JobArtifact.created_at.asc(), JobArtifact.id.asc())
            ).scalars()
        )
        return {
            "job_id": job.id,
            "status": job.status,
            "summary": job.result_summary,
            "error": (
                {
                    "code": job.error_code,
                    "message": job.error_message,
                }
                if job.error_code or job.error_message
                else None
            ),
            "artifacts": [
                {
                    "id": artifact.id,
                    "artifact_type": artifact.artifact_type,
                    "filename": artifact.filename,
                    "storage_key": artifact.storage_key,
                    "size_bytes": artifact.size_bytes,
                }
                for artifact in artifacts
            ],
            "celery_task_id": celery_task_id,
        }
    finally:
        db.close()
