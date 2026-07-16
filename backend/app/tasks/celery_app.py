"""Celery application used by the execution job center."""
from __future__ import annotations

from app.config import get_settings

try:
    from celery import Celery

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

if CELERY_AVAILABLE:
    settings = get_settings()
    app = Celery(
        "airetest",
        broker=settings.CELERY_BROKER_URL or settings.REDIS_URL,
        backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
        include=[
            "app.tasks.api_tasks",
            "app.tasks.ui_tasks",
            "app.tasks.performance_tasks",
        ],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_acks_late=settings.CELERY_TASK_ACKS_LATE,
        worker_prefetch_multiplier=settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
        task_track_started=True,
        task_routes={
            "airetest.jobs.api": {"queue": settings.CELERY_API_QUEUE},
            "airetest.jobs.ui": {"queue": settings.CELERY_UI_QUEUE},
            "airetest.jobs.performance": {
                "queue": settings.CELERY_PERFORMANCE_QUEUE
            },
        },
    )
else:
    app = None
