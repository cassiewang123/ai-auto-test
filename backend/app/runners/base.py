"""执行器抽象层"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RunnerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass
class ExecutionJobSpec:
    """任务执行规格"""

    job_id: str
    job_type: str  # api_case, ui_case, ui_suite, performance
    resource_id: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    max_attempts: int = 1


@dataclass
class RunnerHandle:
    """执行器句柄"""

    job_id: str
    attempt_id: str | None = None
    status: RunnerStatus = RunnerStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class ExecutionArtifacts:
    """执行产物"""

    screenshots: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    traces: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    reports: list[str] = field(default_factory=list)


class ExecutionRunner(ABC):
    """执行器抽象基类"""

    @abstractmethod
    def submit(self, job: ExecutionJobSpec) -> RunnerHandle:
        """提交任务"""
        ...

    @abstractmethod
    def cancel(self, handle: RunnerHandle) -> None:
        """取消任务"""
        ...

    @abstractmethod
    def status(self, handle: RunnerHandle) -> RunnerStatus:
        """查询状态"""
        ...

    @abstractmethod
    def collect(self, handle: RunnerHandle) -> ExecutionArtifacts:
        """收集产物"""
        ...
