"""Celery reliability configuration tests."""
from __future__ import annotations

from app.config import Settings
from app.tasks.celery_app import build_celery_config


def test_celery_reliability_configuration_uses_production_safe_defaults() -> None:
    settings = Settings(
        _env_file=None,
        CELERY_TASK_ACKS_LATE=True,
        CELERY_WORKER_PREFETCH_MULTIPLIER=1,
        CELERY_TASK_TRACK_STARTED=True,
        CELERY_TASK_SEND_SENT_EVENT=True,
        CELERY_WORKER_SEND_TASK_EVENTS=True,
        CELERY_WORKER_MAX_TASKS_PER_CHILD=500,
        CELERY_WORKER_MAX_MEMORY_PER_CHILD=1024,
        CELERY_RESULT_EXPIRES_SECONDS=43200,
        CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP=True,
    )

    config = build_celery_config(settings)

    assert config["task_acks_late"] is True
    assert config["task_track_started"] is True
    assert config["task_send_sent_event"] is True
    assert config["worker_send_task_events"] is True
    assert config["worker_prefetch_multiplier"] == 1
    assert config["worker_max_tasks_per_child"] == 500
    assert config["worker_max_memory_per_child"] == 1024
    assert config["result_expires"] == 43200
    assert config["broker_connection_retry_on_startup"] is True
    assert config["task_routes"]["airetest.jobs.api"] == {
        "queue": "airetest.api"
    }
    assert config["task_routes"]["airetest.jobs.ui"] == {
        "queue": "airetest.ui"
    }
    assert config["task_routes"]["airetest.jobs.performance"] == {
        "queue": "airetest.performance"
    }
