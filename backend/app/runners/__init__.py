"""执行器抽象层.

提供统一的执行器接口（ExecutionRunner），支持多种执行后端：
- LocalProcessRunner：本地进程同步执行（开发环境）
- CeleryRunner（未来）：通过 Celery 分布式执行（生产环境）

统一接口：submit / cancel / status / collect
"""
from app.runners.base import (
    ExecutionArtifacts,
    ExecutionJobSpec,
    ExecutionRunner,
    RunnerHandle,
    RunnerStatus,
)

__all__ = [
    "ExecutionRunner",
    "ExecutionJobSpec",
    "RunnerHandle",
    "RunnerStatus",
    "ExecutionArtifacts",
]
