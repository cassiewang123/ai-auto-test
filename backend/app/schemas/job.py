"""任务中心 API Schema."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobCreate(BaseModel):
    job_type: Literal["api_case", "ui_case", "ui_suite", "performance"]
    resource_id: str | None = None
    config: dict = Field(default_factory=dict)
    project_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    timeout_seconds: int = Field(default=300, ge=1, le=86400)
    max_attempts: int = Field(default=1, ge=1, le=10)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    resource_id: str | None = None
    project_id: str | None = None
    status: str
    priority: int = 0
    created_by: str | None = None
    assigned_worker_id: str | None = None
    timeout_seconds: int = 300
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_summary: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    config: dict[str, Any] = Field(default_factory=dict, exclude=True)
    celery_task_id: str | None = None
    dispatch_mode: str | None = None
    dispatch_queue: str | None = None

    @model_validator(mode="after")
    def populate_dispatch_metadata(self) -> JobResponse:
        metadata = self.config.get("_task_dispatch", {})
        if not isinstance(metadata, dict):
            return self
        task_id = metadata.get("celery_task_id")
        mode = metadata.get("mode")
        queue = metadata.get("queue")
        self.celery_task_id = str(task_id) if task_id else None
        self.dispatch_mode = str(mode) if mode else None
        self.dispatch_queue = str(queue) if queue else None
        return self


class JobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    event_type: str
    sequence: int
    payload: str | None = None
    created_at: datetime | None = None

class JobArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    artifact_type: str
    filename: str | None = None
    storage_key: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None
