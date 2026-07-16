"""Celery task for performance execution jobs."""
from __future__ import annotations

from app.tasks.celery_app import app
from app.tasks.job_task import ExecutionTaskResult, run_execution_job


def _execute_performance_job(
    job_id: str,
    celery_task_id: str | None = None,
) -> ExecutionTaskResult:
    return run_execution_job(job_id, celery_task_id=celery_task_id)


if app is not None:

    @app.task(bind=True, name="airetest.jobs.performance")
    def execute_performance_job(task, job_id: str) -> ExecutionTaskResult:
        return _execute_performance_job(job_id, celery_task_id=task.request.id)

else:
    execute_performance_job = None
