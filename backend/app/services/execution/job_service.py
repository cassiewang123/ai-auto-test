"""统一任务中心服务：JobService.

负责任务的创建、Worker 执行、生命周期管理、事件追加与产物查询。

执行说明：
    execute_job 由 Celery task 或显式配置的本地 fallback 调用。api_case 复用
    test_engine，ui_case 复用 UI execution_service，ui_suite 复用现有套件执行
    辅助，performance 复用 perf_runner。所有执行器统一返回终态、摘要、错误和
    产物描述，由本服务集中写入任务、尝试、事件和 JobArtifact。
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.execution_job import (
    _CANCELLABLE_STATUSES,
    _TERMINAL_STATUSES,
    ExecutionAttempt,
    ExecutionJob,
    JobEvent,
)
from app.models.project_member import ProjectMember
from app.services.execution.job_reporting import RESULT_METRICS_CONFIG_KEY
from app.services.security.data_redaction import redact_sensitive_data

logger = logging.getLogger(__name__)

_DISPATCH_CONFIG_KEY = "_task_dispatch"
_RESULT_STATUSES = {"succeeded", "failed", "timed_out"}


def _now() -> datetime:
    """返回当前 UTC 时间（带时区）。"""
    return datetime.now(timezone.utc)


def _headers_with_cookies(headers: dict, cookies: list[dict]) -> dict:
    """Build an outbound Cookie header from decrypted Cookie records."""
    result = dict(headers or {})
    pairs = [f"{cookie.get('name')}={cookie.get('value', '')}" for cookie in cookies if cookie.get("name")]
    if not pairs:
        return result
    existing = result.get("Cookie") or result.get("cookie") or ""
    cookie_header = "; ".join(pairs)
    result["Cookie"] = f"{existing}; {cookie_header}" if existing else cookie_header
    result.pop("cookie", None)
    return result


class JobService:
    """统一任务中心服务."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #
    def _next_sequence(self, job_id: str) -> int:
        """获取任务下一个事件序列号（按 job 维度单调递增）。"""
        max_seq = (
            self.db.execute(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id)).scalar_one() or 0
        )
        return max_seq + 1

    def _emit_event(
        self,
        job_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> JobEvent:
        """追加一条任务事件。调用方负责提交事务。"""
        safe_payload = redact_sensitive_data(payload) if payload else None
        event = JobEvent(
            job_id=job_id,
            event_type=event_type,
            sequence=self._next_sequence(job_id),
            payload=(json.dumps(safe_payload, ensure_ascii=False, default=str) if safe_payload else None),
        )
        self.db.add(event)
        self.db.flush()
        return event

    # ------------------------------------------------------------------ #
    # 创建
    # ------------------------------------------------------------------ #
    def create_job(
        self,
        job_type: str,
        resource_id: str | None = None,
        config: dict | None = None,
        created_by: str | None = None,
        project_id: str | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
        timeout_seconds: int = 300,
        max_attempts: int = 1,
    ) -> ExecutionJob:
        """创建任务并入队。支持基于 idempotency_key 的幂等创建。"""
        config = redact_sensitive_data(config or {})

        # 幂等：相同 key 已存在则直接返回已有任务
        if idempotency_key:
            existing = self.db.execute(
                select(ExecutionJob).where(
                    ExecutionJob.idempotency_key == idempotency_key,
                    ExecutionJob.created_by == created_by,
                )
            ).scalar_one_or_none()
            if existing:
                return existing

        job = ExecutionJob(
            job_type=job_type,
            resource_id=resource_id,
            project_id=project_id,
            status="queued",
            priority=priority,
            created_by=created_by,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            config=config,
            request_snapshot=json.dumps(config, ensure_ascii=False, default=str),
            idempotency_key=idempotency_key,
            queued_at=_now(),
        )
        self.db.add(job)
        try:
            self.db.flush()
            self._emit_event(
                job.id,
                "job.created",
                {"job_type": job_type, "resource_id": resource_id},
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if idempotency_key:
                existing = self.db.execute(
                    select(ExecutionJob).where(
                        ExecutionJob.idempotency_key == idempotency_key,
                        ExecutionJob.created_by == created_by,
                    )
                ).scalar_one_or_none()
                if existing:
                    return existing
            raise
        self.db.refresh(job)
        return job

    # ------------------------------------------------------------------ #
    # 调度
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_dispatch_metadata(job: ExecutionJob) -> dict[str, Any]:
        """读取持久化在任务配置中的内部调度元数据。"""
        config = job.config if isinstance(job.config, dict) else {}
        metadata = config.get(_DISPATCH_CONFIG_KEY, {})
        return metadata if isinstance(metadata, dict) else {}

    @classmethod
    def get_celery_task_id(cls, job: ExecutionJob) -> str | None:
        """读取 Celery/local 统一任务 ID。"""
        task_id = cls.get_dispatch_metadata(job).get("celery_task_id")
        return str(task_id) if task_id else None

    def record_dispatch(
        self,
        job_id: str,
        *,
        task_id: str,
        queue: str,
        mode: str,
        replace: bool = False,
    ) -> ExecutionJob:
        """在提交队列前持久化 task ID，保证取消和幂等请求可复用。"""
        job = self.db.execute(
            select(ExecutionJob)
            .where(ExecutionJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if not job:
            raise ValueError(f"Job '{job_id}' 不存在")
        existing = self.get_celery_task_id(job)
        if existing and not replace:
            self.db.commit()
            self.db.refresh(job)
            return job
        if job.status != "queued":
            self.db.commit()
            self.db.refresh(job)
            return job

        config = dict(job.config or {})
        config[_DISPATCH_CONFIG_KEY] = {
            "celery_task_id": task_id,
            "queue": queue,
            "mode": mode,
            "dispatched_at": _now().isoformat(),
        }
        job.config = config
        self._emit_event(
            job.id,
            "job.dispatched",
            {"celery_task_id": task_id, "queue": queue, "mode": mode},
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_dispatch_failed(self, job_id: str, error_message: str) -> ExecutionJob:
        """将无法投递的 queued 任务置为失败，不覆盖已开始或已取消状态。"""
        job = self.db.execute(
            select(ExecutionJob)
            .where(ExecutionJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if not job:
            raise ValueError(f"Job '{job_id}' 不存在")
        if job.status != "queued":
            return job

        job.status = "failed"
        job.finished_at = _now()
        job.error_code = "dispatch_failed"
        job.error_message = redact_sensitive_data(error_message)
        self._emit_event(
            job.id,
            "job.failed",
            {"status": "failed", "error_code": "dispatch_failed"},
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def record_revoke_result(
        self,
        job_id: str,
        *,
        task_id: str,
        revoked: bool,
        error_message: str | None = None,
    ) -> None:
        """记录队列撤销结果，任务状态已由 cancel_job 固化。"""
        job = self.get_job(job_id)
        if not job:
            return
        self._emit_event(
            job.id,
            "job.revoke_requested",
            {
                "celery_task_id": task_id,
                "revoked": revoked,
                "error_message": error_message,
            },
        )
        self.db.commit()

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def get_job(self, job_id: str) -> ExecutionJob | None:
        """按 ID 查询任务，不存在返回 None。"""
        return self.db.get(ExecutionJob, job_id)

    def list_jobs(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        job_type: str | None = None,
        user_id: str | None = None,
        is_superuser: bool = False,
    ) -> tuple[list[ExecutionJob], int]:
        """分页查询任务列表，返回 (任务列表, 总数)。"""
        query = select(ExecutionJob)
        if user_id and not is_superuser:
            member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
            query = query.where(
                or_(
                    ExecutionJob.created_by == user_id,
                    ExecutionJob.project_id.in_(member_projects),
                )
            )
        if status:
            query = query.where(ExecutionJob.status == status)
        if job_type:
            query = query.where(ExecutionJob.job_type == job_type)
        query = query.order_by(ExecutionJob.created_at.desc())

        total = self.db.execute(select(func.count()).select_from(query.subquery())).scalar_one()

        offset = (page - 1) * page_size
        jobs = list(self.db.execute(query.offset(offset).limit(page_size)).scalars().all())
        return jobs, total

    def get_events(self, job_id: str, after_sequence: int = 0) -> list[JobEvent]:
        """增量查询任务事件（sequence > after_sequence，按序列升序）。"""
        return list(
            self.db.execute(
                select(JobEvent)
                .where(
                    JobEvent.job_id == job_id,
                    JobEvent.sequence > after_sequence,
                )
                .order_by(JobEvent.sequence.asc())
            )
            .scalars()
            .all()
        )

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #
    def execute_job(
        self,
        job_id: str,
        *,
        worker_id: str | None = None,
    ) -> ExecutionJob:
        """由 Worker 执行任务，并保证重复投递不会让状态回退。

        流程：
            1. 校验任务状态为 queued
            2. 置为 running，创建 attempt，发送 job.started 事件
            3. 按 job_type 执行（api_case 复用 test_engine）
            4. 置为终态，发送 job.completed / job.failed 事件
        """
        job = self.db.execute(
            select(ExecutionJob)
            .where(ExecutionJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if not job:
            raise ValueError(f"Job '{job_id}' 不存在")
        if job.status != "queued":
            return job

        worker_id = (worker_id or f"worker-{uuid.uuid4().hex[:8]}")[:64]
        started_at = _now()
        job.status = "running"
        job.started_at = started_at
        job.assigned_worker_id = worker_id
        job.attempt_count = (job.attempt_count or 0) + 1

        attempt = ExecutionAttempt(
            job_id=job.id,
            attempt_number=job.attempt_count,
            status="running",
            worker_id=worker_id,
            started_at=started_at,
        )
        self.db.add(attempt)
        self.db.flush()
        self._emit_event(
            job.id,
            "job.started",
            {"attempt": job.attempt_count, "worker_id": worker_id},
        )
        self.db.commit()

        # 执行（捕获所有异常以保证终态落库）
        start_ts = time.perf_counter()
        result_status = "succeeded"
        result_summary: str | None = None
        error_code: str | None = None
        error_message: str | None = None
        artifacts: list[dict[str, Any]] = []
        result_metrics: dict[str, Any] = {}
        try:
            run_result = self._run(job)
            result_status = run_result.get("status", "succeeded")
            result_summary = run_result.get("summary")
            error_code = run_result.get("error_code")
            error_message = run_result.get("error_message")
            raw_metrics = run_result.get("metrics")
            if isinstance(raw_metrics, dict):
                result_metrics = raw_metrics
            raw_artifacts = run_result.get("artifacts", [])
            if isinstance(raw_artifacts, list):
                artifacts = [
                    artifact
                    for artifact in raw_artifacts
                    if isinstance(artifact, dict)
                ]
        except Exception as exc:  # noqa: BLE001 - 记录错误并置失败
            logger.exception("Job %s 执行失败", job_id)
            result_status = (
                "timed_out" if self._is_timeout_exception(exc) else "failed"
            )
            error_code = (
                "timeout" if result_status == "timed_out" else type(exc).__name__
            )
            error_message = str(exc)

        duration = time.perf_counter() - start_ts
        finished_at = _now()
        if (
            job.timeout_seconds
            and duration >= job.timeout_seconds
            and result_status != "timed_out"
        ):
            result_status = "timed_out"
            error_code = "timeout"
            error_message = (
                f"任务执行超过 {job.timeout_seconds} 秒超时限制"
            )
            if not result_summary:
                result_summary = "任务执行超时"

        # 取消请求可能在执行期间由另一个 Session 提交。刷新后必须保留 cancelled，
        # 不能让较晚完成的 Worker 把状态覆盖回 succeeded/failed。
        job = self.db.execute(
            select(ExecutionJob)
            .where(ExecutionJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        persisted_artifacts = self._persist_artifacts(job.id, artifacts)
        if job.status == "cancelled":
            attempt.status = "cancelled"
            attempt.finished_at = finished_at
            attempt.duration_seconds = round(duration, 4)
            self.db.commit()
            self.db.refresh(job)
            return job

        if result_status not in _RESULT_STATUSES:
            error_code = "invalid_result_status"
            error_message = f"执行器返回了不支持的状态: {result_status}"
            result_status = "failed"
        if not result_summary:
            result_summary = {
                "succeeded": "任务执行完成",
                "failed": "任务执行失败",
                "timed_out": "任务执行超时",
            }[result_status]

        result_summary = redact_sensitive_data(result_summary)
        error_message = redact_sensitive_data(error_message)
        if not result_metrics:
            result_metrics = {
                "total": 1,
                "passed": 1 if result_status == "succeeded" else 0,
                "failed": 1 if result_status == "failed" else 0,
                "error": 1 if result_status == "timed_out" else 0,
                "skipped": 0,
                "duration": round(duration, 4),
                "results": [],
            }
        result_metrics = redact_sensitive_data(result_metrics)
        config = dict(job.config or {})
        config[RESULT_METRICS_CONFIG_KEY] = result_metrics
        job.config = config
        job.status = result_status
        job.finished_at = finished_at
        job.result_summary = result_summary
        if error_code:
            job.error_code = error_code
        if error_message:
            job.error_message = error_message

        attempt.status = result_status
        attempt.finished_at = finished_at
        attempt.duration_seconds = round(duration, 4)
        attempt.result_summary = result_summary
        attempt.error_code = error_code
        attempt.error_message = error_message

        if result_status == "succeeded":
            terminal_event = "job.completed"
        elif result_status == "timed_out":
            terminal_event = "job.timed_out"
        else:
            terminal_event = "job.failed"
        self._emit_event(
            job.id,
            terminal_event,
            {
                "status": result_status,
                "duration": round(duration, 4),
                "summary": result_summary,
                "error_code": error_code,
                "error_message": error_message,
                "artifacts": persisted_artifacts,
                "metrics": result_metrics,
            },
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    @staticmethod
    def _is_timeout_exception(exc: Exception) -> bool:
        """识别 Python、Celery/billiard 和执行器抛出的超时异常。"""
        return isinstance(exc, TimeoutError) or type(exc).__name__ in {
            "SoftTimeLimitExceeded",
            "TimeLimitExceeded",
        }

    def _persist_artifacts(
        self,
        job_id: str,
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """将统一产物描述写入 JobArtifact，并返回可序列化摘要。"""
        from app.models.job_artifact import JobArtifact

        persisted: list[dict[str, Any]] = []
        for artifact in artifacts:
            artifact_type = str(artifact.get("artifact_type") or "").strip()
            if not artifact_type:
                continue
            filename = artifact.get("filename")
            storage_key = artifact.get("storage_key")
            size_bytes = artifact.get("size_bytes")
            row = JobArtifact(
                job_id=job_id,
                artifact_type=artifact_type[:64],
                filename=str(filename)[:512] if filename else None,
                storage_key=str(storage_key)[:512] if storage_key else None,
                size_bytes=int(size_bytes) if size_bytes is not None else None,
            )
            self.db.add(row)
            self.db.flush()
            item = {
                "id": row.id,
                "artifact_type": row.artifact_type,
                "filename": row.filename,
                "storage_key": row.storage_key,
                "size_bytes": row.size_bytes,
            }
            persisted.append(item)
            self._emit_event(job_id, "job.artifact.created", item)
        return persisted

    def _run(self, job: ExecutionJob) -> dict[str, Any]:
        """按 job_type 派发执行，返回结果字典。

        返回结构：
            {
                "status": "succeeded"|"failed"|"timed_out",
                "summary": str|None,
                "error_code": str|None,
                "error_message": str|None,
                "artifacts": list[dict],
                "metrics": dict,
            }
        """
        if job.job_type == "api_case":
            return self._run_api_case(job)
        if job.job_type == "ui_case":
            return self._run_ui_case(job)
        if job.job_type == "ui_suite":
            return self._run_ui_suite(job)
        if job.job_type == "performance":
            return self._run_performance(job)
        raise ValueError(f"不支持的任务类型: {job.job_type}")

    def _run_api_case(self, job: ExecutionJob) -> dict[str, Any]:
        """执行接口用例：加载 TestCase 并通过 test_engine 运行。"""
        from test_engine.executor import TestCaseExecutor
        from test_engine.request_builder import RequestBuilder

        from app.models.test_case import TestCase
        from app.schemas.execution import RequestDefinition
        from app.services.security.secret_crypto import decrypt_cookies
        from app.services.security.url_policy import URLPolicy

        if not job.resource_id:
            raise ValueError("api_case 任务缺少 resource_id")

        case = self.db.get(TestCase, job.resource_id)
        if not case:
            raise ValueError(f"TestCase '{job.resource_id}' 不存在")

        # 解析环境基址 URL、变量与会话 Cookie
        url = case.url
        variables: dict[str, Any] = {}
        environment_cookies: list[dict] = []
        if case.environment_id:
            from app.models.environment import Environment

            env = self.db.get(Environment, case.environment_id)
            if env:
                variables = dict(env.variables or {})
                environment_cookies = decrypt_cookies(env.cookies)
            if env and env.base_url and not url.startswith("http"):
                url = f"{env.base_url.rstrip('/')}/{url.lstrip('/')}"

        settings = get_settings()
        url_policy = URLPolicy(
            allow_private=settings.URL_ALLOW_PRIVATE,
            allowed_domains=[d.strip() for d in settings.URL_ALLOWED_DOMAINS.split(",") if d.strip()],
            blocked_domains=[d.strip() for d in settings.URL_BLOCKED_DOMAINS.split(",") if d.strip()],
        )
        executor = TestCaseExecutor(
            request_builder=RequestBuilder(
                url_policy=url_policy,
                max_response_size=settings.URL_MAX_RESPONSE_SIZE,
            )
        )

        request_def = RequestDefinition(
            method=case.method,
            url=url,
            headers=_headers_with_cookies(
                case.headers or {},
                environment_cookies,
            ),
            params=case.params or {},
            body=case.body,
            graphql_query=case.graphql_query,
            extract_rules=case.extract_rules or [],
            timeout=30.0,
        )
        assertions = [
            {
                "assertion_type": a.assertion_type,
                "expression": a.expression,
                "operator": a.operator,
                "expected": a.expected,
                "priority": a.priority,
                "order": a.order,
            }
            for a in sorted(case.assertions, key=lambda x: x.order)
        ]

        result = executor.execute(
            request_def=request_def,
            assertions=assertions,
            variables=variables,
            test_case_id=case.id,
        )

        self._emit_event(
            job.id,
            "job.log",
            {
                "status": result.status,
                "duration": round(result.duration, 4),
                "status_code": result.response.status_code if result.response else None,
                "error": result.error_message,
            },
        )

        # passed -> succeeded；failed/error -> failed
        status_code = result.response.status_code if result.response else None
        metrics = {
            "total": 1,
            "passed": 1 if result.status == "passed" else 0,
            "failed": 1 if result.status == "failed" else 0,
            "error": 1 if result.status not in {"passed", "failed"} else 0,
            "skipped": 0,
            "duration": round(result.duration, 4),
            "status_code": status_code,
            "results": [
                {
                    "case_id": case.id,
                    "title": case.title,
                    "method": case.method,
                    "url": case.url,
                    "status": result.status,
                    "duration": round(result.duration, 4),
                    "status_code": status_code,
                    "error": result.error_message,
                }
            ],
        }
        if result.status == "passed":
            return {
                "status": "succeeded",
                "summary": f"用例执行通过（{result.duration:.2f}s）",
                "metrics": metrics,
            }
        return {
            "status": "failed",
            "summary": f"用例执行{result.status}（{result.duration:.2f}s）",
            "error_code": result.status,
            "error_message": result.error_message or f"用例执行状态：{result.status}",
            "metrics": metrics,
        }

    def _run_ui_case(self, job: ExecutionJob) -> dict[str, Any]:
        """通过现有 Playwright execution_service 执行单个 UI 用例。"""
        from app.models.ui_test_case import UiTestCase
        from app.models.ui_test_record import UiTestRecord
        from app.services.ui.execution_service import execute_ui_case

        if not job.resource_id:
            raise ValueError("ui_case 任务缺少 resource_id")
        case = self.db.get(UiTestCase, job.resource_id)
        if not case:
            raise ValueError(f"UiTestCase '{job.resource_id}' 不存在")

        artifact_dir = self._job_artifact_dir(job.id)
        started = time.perf_counter()
        result, retry_attempts, final_attempt = execute_ui_case(
            url=case.url,
            browser_type=case.browser_type or "chrome",
            steps=case.steps or [],
            retry_count=case.retry_count or 0,
            retry_interval=(
                case.retry_interval
                if case.retry_interval is not None
                else 2.0
            ),
            db=self.db,
            job_id=job.id,
            artifact_dir=str(artifact_dir),
        )
        duration = round(time.perf_counter() - started, 3)

        record = UiTestRecord(
            case_id=case.id,
            case_title=case.title,
            project_id=case.project_id,
            url=case.url,
            browser_type=case.browser_type or "chrome",
            status=result.get("status", "error"),
            total_steps=int(result.get("total_steps") or 0),
            passed_steps=int(result.get("passed_steps") or 0),
            failed_steps=int(result.get("failed_steps") or 0),
            duration=duration,
            error=result.get("error"),
            step_results=result.get("steps") or [],
            retry_attempts=retry_attempts,
            final_attempt=final_attempt,
            triggered_by=f"job:{job.id}",
        )
        self.db.add(record)
        self.db.flush()

        artifacts = self._write_screenshot_artifacts(
            job.id,
            result.get("screenshots"),
            prefix=f"ui_case_{case.id}",
        )
        trace_path = result.get("trace_path")
        if trace_path:
            trace_artifact = self._file_artifact(trace_path, "trace")
            if trace_artifact:
                artifacts.append(trace_artifact)

        ui_status = str(result.get("status") or "error")
        succeeded = ui_status == "passed"
        self._emit_event(
            job.id,
            "job.log",
            {
                "record_id": record.id,
                "status": ui_status,
                "total_steps": record.total_steps,
                "passed_steps": record.passed_steps,
                "failed_steps": record.failed_steps,
                "duration": duration,
                "final_attempt": final_attempt,
            },
        )
        return {
            "status": "succeeded" if succeeded else "failed",
            "summary": (
                f"UI 用例执行{'通过' if succeeded else '失败'}："
                f"{record.passed_steps}/{record.total_steps} 步通过"
                f"（{duration:.2f}s）"
            ),
            "error_code": None if succeeded else ui_status,
            "error_message": None if succeeded else (
                result.get("error") or f"UI 用例执行状态：{ui_status}"
            ),
            "artifacts": artifacts,
            "metrics": {
                "total": record.total_steps,
                "passed": record.passed_steps,
                "failed": record.failed_steps,
                "error": max(
                    record.total_steps - record.passed_steps - record.failed_steps,
                    0,
                ),
                "skipped": 0,
                "duration": duration,
                "results": [
                    {
                        "case_id": case.id,
                        "title": case.title,
                        "method": "UI",
                        "url": case.url,
                        "status": ui_status,
                        "duration": duration,
                        "status_code": None,
                        "error": result.get("error"),
                    }
                ],
            },
        }

    def _run_ui_suite(self, job: ExecutionJob) -> dict[str, Any]:
        """复用现有 UI 套件单例执行辅助并持久化套件运行记录。"""
        from app.api.v1.ui_test_suites import (
            _build_record_from_result,
            _execute_single_case,
        )
        from app.models.ui_test_case import UiTestCase
        from app.models.ui_test_suite import UiTestSuite, UiTestSuiteRun
        from app.services.ui.execution_service import _expand_step_groups

        if not job.resource_id:
            raise ValueError("ui_suite 任务缺少 resource_id")
        suite = self.db.get(UiTestSuite, job.resource_id)
        if not suite:
            raise ValueError(f"UiTestSuite '{job.resource_id}' 不存在")

        case_ids = list(suite.case_ids or [])
        cases_by_id = {
            case.id: case
            for case in self.db.execute(
                select(UiTestCase).where(
                    UiTestCase.id.in_(case_ids),
                    UiTestCase.is_active.is_(True),
                )
            ).scalars()
        } if case_ids else {}
        cases = [cases_by_id[case_id] for case_id in case_ids if case_id in cases_by_id]
        if not cases:
            raise ValueError("UI 套件没有可执行的活动用例")

        execution_mode = suite.execution_mode or "sequential"
        max_workers = max(int(suite.max_workers or 4), 1)
        retry_enabled = (
            suite.retry_enabled if suite.retry_enabled is not None else True
        )
        case_steps_pairs = [
            (case, _expand_step_groups(case.steps or [], self.db))
            for case in cases
        ]

        suite_run = UiTestSuiteRun(
            suite_id=suite.id,
            suite_name=suite.name,
            project_id=suite.project_id,
            total=len(cases),
            passed=0,
            failed=0,
            status="running",
            record_ids=[],
            triggered_by=f"job:{job.id}",
            execution_mode=execution_mode,
            max_workers=(
                min(max_workers, len(cases))
                if execution_mode == "parallel"
                else 1
            ),
            retry_enabled=retry_enabled,
        )
        self.db.add(suite_run)
        self.db.flush()

        started = time.perf_counter()
        results: list[dict[str, Any]] = []
        if execution_mode == "parallel":
            with ThreadPoolExecutor(max_workers=suite_run.max_workers) as executor:
                future_to_case = {
                    executor.submit(
                        _execute_single_case,
                        case,
                        steps,
                        case.retry_count if retry_enabled else 0,
                        (
                            case.retry_interval
                            if case.retry_interval is not None
                            else 2.0
                        ),
                    ): case
                    for case, steps in case_steps_pairs
                }
                for future in as_completed(future_to_case):
                    case = future_to_case[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:  # noqa: BLE001
                        results.append(
                            self._failed_suite_case_result(case, exc)
                        )
        else:
            for case, steps in case_steps_pairs:
                try:
                    results.append(
                        _execute_single_case(
                            case,
                            steps,
                            case.retry_count if retry_enabled else 0,
                            (
                                case.retry_interval
                                if case.retry_interval is not None
                                else 2.0
                            ),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    results.append(self._failed_suite_case_result(case, exc))

        duration = round(time.perf_counter() - started, 3)
        record_ids: list[str] = []
        passed_count = 0
        failed_count = 0
        serial_estimate = 0.0
        total_retries = 0
        retried_cases: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []

        for result in results:
            serial_estimate += float(result.get("duration") or 0.0)
            record = _build_record_from_result(result, suite.name)
            record.triggered_by = f"job:{job.id}"
            self.db.add(record)
            self.db.flush()
            record_ids.append(record.id)
            if result.get("status") == "passed":
                passed_count += 1
            else:
                failed_count += 1

            attempts = result.get("retry_attempts") or []
            if len(attempts) > 1:
                total_retries += len(attempts) - 1
                retried_cases.append(
                    {
                        "case_id": result["case_id"],
                        "case_title": result["case_title"],
                        "attempts": len(attempts),
                        "final_status": result.get("status"),
                    }
                )
            artifacts.extend(
                self._write_screenshot_artifacts(
                    job.id,
                    result.get("screenshots"),
                    prefix=f"ui_suite_{suite.id}_{result['case_id']}",
                )
            )

        suite_run.passed = passed_count
        suite_run.failed = failed_count
        suite_run.duration = duration
        suite_run.record_ids = record_ids
        suite_run.status = "completed"
        suite_run.finished_at = datetime.now()
        suite_run.total_retries = total_retries
        suite_run.retried_cases = retried_cases
        if execution_mode == "parallel":
            suite_run.parallel_duration = round(serial_estimate, 3)

        report = self._write_json_artifact(
            job.id,
            f"ui_suite_{suite.id}_{suite_run.id}.json",
            {
                "run_id": suite_run.id,
                "suite_id": suite.id,
                "suite_name": suite.name,
                "total": suite_run.total,
                "passed": passed_count,
                "failed": failed_count,
                "duration": duration,
                "execution_mode": execution_mode,
                "record_ids": record_ids,
                "total_retries": total_retries,
            },
        )
        artifacts.append(report)
        self._emit_event(
            job.id,
            "job.log",
            {
                "run_id": suite_run.id,
                "status": "passed" if failed_count == 0 else "failed",
                "total": suite_run.total,
                "passed": passed_count,
                "failed": failed_count,
                "duration": duration,
            },
        )

        succeeded = failed_count == 0
        first_error = next(
            (
                str(result.get("error"))
                for result in results
                if result.get("error")
            ),
            None,
        )
        return {
            "status": "succeeded" if succeeded else "failed",
            "summary": (
                f"UI 套件执行{'通过' if succeeded else '失败'}："
                f"{passed_count}/{len(results)} 个用例通过"
                f"（{duration:.2f}s）"
            ),
            "error_code": None if succeeded else "ui_suite_failed",
            "error_message": None if succeeded else (
                first_error or f"{failed_count} 个 UI 用例执行失败"
            ),
            "artifacts": artifacts,
            "metrics": {
                "total": suite_run.total,
                "passed": passed_count,
                "failed": failed_count,
                "error": 0,
                "skipped": 0,
                "duration": duration,
                "results": [
                    {
                        "case_id": result.get("case_id"),
                        "title": result.get("case_title"),
                        "method": "UI",
                        "url": result.get("url"),
                        "status": result.get("status"),
                        "duration": round(float(result.get("duration") or 0.0), 4),
                        "status_code": None,
                        "error": result.get("error"),
                    }
                    for result in results
                ],
            },
        }

    def _run_performance(self, job: ExecutionJob) -> dict[str, Any]:
        """同步调用 perf_runner，并将持久化压测结果映射为统一任务结果。"""
        from app.models.performance_result import PerformanceResult
        from app.models.performance_test import PerformanceTest
        from app.services import perf_realtime
        from app.services.perf_runner import execute_performance_test

        if not job.resource_id:
            raise ValueError("performance 任务缺少 resource_id")
        test = self.db.get(PerformanceTest, job.resource_id)
        if not test:
            raise ValueError(f"PerformanceTest '{job.resource_id}' 不存在")

        test_id = test.id
        self.db.rollback()
        run_id = execute_performance_test(test_id, run_id=job.id)
        self.db.expire_all()
        result = self.db.execute(
            select(PerformanceResult).where(
                PerformanceResult.test_id == test_id,
                PerformanceResult.run_id == run_id,
            )
        ).scalar_one_or_none()
        realtime = perf_realtime.get(test_id)
        realtime_for_run = (
            realtime
            if realtime and realtime.get("run_id") == run_id
            else None
        )
        if result is None:
            error_message = (
                realtime_for_run.get("error")
                if realtime_for_run
                else None
            ) or "性能执行未产生结果记录"
            self._emit_event(
                job.id,
                "job.log",
                {
                    "run_id": run_id,
                    "status": (
                        realtime_for_run.get("status")
                        if realtime_for_run
                        else "failed"
                    ),
                    "error": error_message,
                },
            )
            return {
                "status": "failed",
                "summary": "性能测试执行失败",
                "error_code": "performance_failed",
                "error_message": error_message,
                "artifacts": [],
                "metrics": {
                    "total": 1,
                    "passed": 0,
                    "failed": 0,
                    "error": 1,
                    "skipped": 0,
                    "duration": 0.0,
                    "results": [],
                },
            }

        failed_reason: str | None = None
        if result.sla_status == "failed":
            failed_reason = "性能测试未满足 SLA"
        elif result.total_requests <= 0:
            failed_reason = "性能测试未产生请求"
        elif result.success_requests <= 0 and result.fail_requests > 0:
            failed_reason = "性能测试请求全部失败"

        report = self._write_json_artifact(
            job.id,
            f"performance_{run_id}.json",
            {
                "result_id": result.id,
                "test_id": result.test_id,
                "run_id": result.run_id,
                "total_requests": result.total_requests,
                "success_requests": result.success_requests,
                "fail_requests": result.fail_requests,
                "avg_response_time": result.avg_response_time,
                "p95": result.p95,
                "p99": result.p99,
                "rps": result.rps,
                "error_rate": result.error_rate,
                "duration": result.duration,
                "sla_status": result.sla_status,
                "sla_details": result.sla_details,
                "mode": result.mode,
            },
        )
        self._emit_event(
            job.id,
            "job.log",
            {
                "result_id": result.id,
                "run_id": run_id,
                "status": "failed" if failed_reason else "passed",
                "total_requests": result.total_requests,
                "success_requests": result.success_requests,
                "fail_requests": result.fail_requests,
                "p95": result.p95,
                "rps": result.rps,
                "sla_status": result.sla_status,
            },
        )
        return {
            "status": "failed" if failed_reason else "succeeded",
            "summary": (
                f"性能测试{'失败' if failed_reason else '完成'}："
                f"{result.total_requests} 请求，"
                f"{result.success_requests} 成功，{result.fail_requests} 失败，"
                f"P95 {result.p95:.2f}ms，RPS {result.rps:.2f}"
            ),
            "error_code": "performance_assertion_failed" if failed_reason else None,
            "error_message": failed_reason,
            "artifacts": [report],
            "metrics": {
                "total": result.total_requests,
                "passed": result.success_requests,
                "failed": result.fail_requests,
                "error": 0,
                "skipped": 0,
                "duration": result.duration,
                "p95": result.p95,
                "p99": result.p99,
                "rps": result.rps,
                "error_rate": result.error_rate,
                "sla_status": result.sla_status,
                "results": [
                    {
                        "case_id": test.id,
                        "title": test.name,
                        "method": "PERF",
                        "url": f"performance://{test.name}",
                        "status": "failed" if failed_reason else "passed",
                        "duration": result.duration,
                        "status_code": None,
                        "error": failed_reason,
                    }
                ],
            },
        }

    @staticmethod
    def _failed_suite_case_result(case: Any, exc: Exception) -> dict[str, Any]:
        """将单个套件用例异常转换为现有套件记录协议。"""
        return {
            "case_id": case.id,
            "case_title": case.title,
            "project_id": case.project_id,
            "url": case.url,
            "browser_type": case.browser_type or "chrome",
            "status": "error",
            "total_steps": 0,
            "passed_steps": 0,
            "failed_steps": 0,
            "duration": 0.0,
            "error": f"套件用例执行异常: {exc}",
            "step_results": [],
            "screenshots": [],
            "started_at": datetime.now(),
            "retry_attempts": [],
            "final_attempt": 1,
        }

    @staticmethod
    def _job_artifact_dir(job_id: str) -> Path:
        from app.services.ui.artifact_service import get_artifact_root

        path = get_artifact_root() / "jobs" / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_screenshot_artifacts(
        self,
        job_id: str,
        screenshots: Any,
        *,
        prefix: str,
    ) -> list[dict[str, Any]]:
        """将 UI 引擎返回的 base64 截图保存到统一产物目录。"""
        if not isinstance(screenshots, list):
            return []
        artifact_dir = self._job_artifact_dir(job_id)
        artifacts: list[dict[str, Any]] = []
        for index, screenshot in enumerate(screenshots, start=1):
            if not isinstance(screenshot, str) or not screenshot:
                continue
            encoded = screenshot.split(",", 1)[-1]
            try:
                content = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError, TypeError):
                logger.warning(
                    "Job %s 返回了无效的 base64 截图，已跳过",
                    job_id,
                )
                continue
            path = artifact_dir / f"{prefix}_{index}.png"
            path.write_bytes(content)
            artifact = self._file_artifact(path, "screenshot")
            if artifact:
                artifacts.append(artifact)
        return artifacts

    def _write_json_artifact(
        self,
        job_id: str,
        filename: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """写入精简 JSON 报告并返回统一产物描述。"""
        path = self._job_artifact_dir(job_id) / filename
        safe_payload = redact_sensitive_data(payload)
        path.write_text(
            json.dumps(safe_payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        artifact = self._file_artifact(path, "report")
        if artifact is None:
            raise RuntimeError(f"无法创建任务产物: {path}")
        return artifact

    @staticmethod
    def _file_artifact(
        file_path: str | Path,
        artifact_type: str,
    ) -> dict[str, Any] | None:
        """将允许目录内的真实文件转换为 JobArtifact 描述。"""
        from app.services.ui.artifact_service import get_artifact_root

        path = Path(file_path).resolve()
        if not path.is_file():
            return None
        root = get_artifact_root()
        try:
            storage_key = path.relative_to(root).as_posix()
        except ValueError:
            logger.warning("忽略产物目录外文件: %s", path)
            return None
        return {
            "artifact_type": artifact_type,
            "filename": path.name,
            "storage_key": storage_key,
            "size_bytes": path.stat().st_size,
        }

    # ------------------------------------------------------------------ #
    # 取消
    # ------------------------------------------------------------------ #
    def cancel_job(self, job_id: str) -> ExecutionJob:
        """请求取消任务。仅 queued/running 可取消，否则抛出 ValueError。"""
        job = self.db.execute(
            select(ExecutionJob)
            .where(ExecutionJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if not job:
            raise ValueError(f"Job '{job_id}' 不存在")
        if job.status not in _CANCELLABLE_STATUSES:
            raise ValueError(f"任务当前状态为 '{job.status}'，无法取消")

        previous_status = job.status
        job.status = "cancelled"
        job.finished_at = _now()
        self._emit_event(
            job.id,
            "job.cancelled",
            {
                "previous_status": previous_status,
                "celery_task_id": self.get_celery_task_id(job),
            },
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    # ------------------------------------------------------------------ #
    # 终态判断（供 WebSocket 使用）
    # ------------------------------------------------------------------ #
    @staticmethod
    def is_terminal(status: str | None) -> bool:
        """判断状态是否为终态。"""
        return status in _TERMINAL_STATUSES
