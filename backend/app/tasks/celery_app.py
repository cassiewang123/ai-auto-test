"""Celery application used by the execution job center."""
from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings

try:
    from celery import Celery

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


def build_celery_config(settings: Settings | None = None) -> dict[str, Any]:
    """Return the Celery reliability and routing configuration."""
    current = settings or get_settings()
    return {
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "timezone": "Asia/Shanghai",
        "enable_utc": True,
        "task_acks_late": current.CELERY_TASK_ACKS_LATE,
        "task_track_started": current.CELERY_TASK_TRACK_STARTED,
        "task_send_sent_event": current.CELERY_TASK_SEND_SENT_EVENT,
        "worker_prefetch_multiplier": current.CELERY_WORKER_PREFETCH_MULTIPLIER,
        "worker_send_task_events": current.CELERY_WORKER_SEND_TASK_EVENTS,
        "worker_max_tasks_per_child": current.CELERY_WORKER_MAX_TASKS_PER_CHILD,
        "worker_max_memory_per_child": current.CELERY_WORKER_MAX_MEMORY_PER_CHILD,
        "result_expires": current.CELERY_RESULT_EXPIRES_SECONDS,
        "broker_connection_retry_on_startup": (
            current.CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP
        ),
        "task_routes": {
            "airetest.jobs.api": {"queue": current.CELERY_API_QUEUE},
            "airetest.jobs.ui": {"queue": current.CELERY_UI_QUEUE},
            "airetest.jobs.performance": {
                "queue": current.CELERY_PERFORMANCE_QUEUE
            },
        },
    }


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
    app.conf.update(build_celery_config(settings))
else:
    app = None
