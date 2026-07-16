"""统一任务中心 API

端点：
    POST   /jobs              — 创建并投递任务
    GET    /jobs              — 分页查询任务列表
    GET    /jobs/{id}         — 查询任务详情
    POST   /jobs/{id}/cancel  — 请求取消任务
    POST   /jobs/{id}/retry   — 手动重试任务
    GET    /jobs/{id}/events  — 增量查询事件
    GET    /jobs/{id}/artifacts — 查询产物
    WS     /jobs/{id}/stream  — 实时日志和状态（WebSocket）

鉴权说明：
    HTTP 端点通过 Depends(get_current_user) 进行 JWT 鉴权。
    WebSocket 端点不能使用 Depends（浏览器无法在握手时设置 Authorization
    头），因此在端点内部从查询参数 token 手动验证 JWT。
"""
import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ForbiddenError, NotFoundError
from app.database import get_db
from app.models.execution_job import ExecutionJob
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.schemas.job import JobArtifactResponse, JobCreate, JobEventResponse, JobResponse
from app.services.auth_service import get_current_user
from app.services.execution.job_dispatcher import JobDispatcher, JobDispatchError
from app.services.execution.job_service import JobService
from app.services.project_access import ensure_job_access, ensure_project_role

router = APIRouter()


def _dispatch_queued_job(
    db: Session,
    service: JobService,
    job: ExecutionJob,
) -> ExecutionJob:
    """Dispatch a queued job and refresh the API session after eager execution."""
    if job.status != "queued":
        return job
    dispatcher = JobDispatcher.from_session(db)
    try:
        dispatcher.dispatch(job, service)
    except JobDispatchError as exc:
        refreshed = service.get_job(job.id)
        if refreshed and refreshed.status == "queued":
            service.mark_dispatch_failed(job.id, str(exc))
        raise AppException(
            status_code=503,
            message="任务投递失败",
            detail=str(exc),
        ) from exc
    db.expire_all()
    return service.get_job(job.id) or job


def _resolve_resource_project(
    db: Session,
    job_type: str,
    resource_id: str | None,
    requested_project_id: str | None,
) -> str | None:
    """Derive project ownership from the referenced execution resource."""
    if not resource_id:
        return requested_project_id

    model: type[Any] | None = None
    if job_type == "api_case":
        from app.models.test_case import TestCase

        model = TestCase
    elif job_type == "ui_case":
        from app.models.ui_test_case import UiTestCase

        model = UiTestCase
    elif job_type == "ui_suite":
        from app.models.ui_test_suite import UiTestSuite

        model = UiTestSuite
    elif job_type == "performance":
        from app.models.performance_test import PerformanceTest

        model = PerformanceTest

    if model is None:
        raise AppException(f"不支持的任务类型: {job_type}", status_code=422)

    resource = db.get(model, resource_id)
    if not resource:
        raise NotFoundError(model.__name__, resource_id)
    resource_project_id = getattr(resource, "project_id", None)
    if (
        requested_project_id
        and resource_project_id
        and requested_project_id != resource_project_id
    ):
        raise AppException("任务 project_id 与资源所属项目不一致", status_code=422)
    return resource_project_id or requested_project_id


@router.post("", response_model=DataResponse[JobResponse])
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建统一任务并投递到对应执行队列。"""
    project_id = _resolve_resource_project(
        db,
        payload.job_type,
        payload.resource_id,
        payload.project_id,
    )
    if project_id:
        ensure_project_role(db, current_user, project_id, "tester")

    service = JobService(db)
    job = service.create_job(
        job_type=payload.job_type,
        resource_id=payload.resource_id,
        config=payload.config,
        created_by=current_user.id,
        project_id=project_id,
        idempotency_key=payload.idempotency_key,
        timeout_seconds=payload.timeout_seconds,
        max_attempts=payload.max_attempts,
    )
    job = _dispatch_queued_job(db, service, job)
    return DataResponse(data=JobResponse.model_validate(job))


@router.get("", response_model=PageResponse[JobResponse])
def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    job_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页查询任务列表"""
    service = JobService(db)
    jobs, total = service.list_jobs(
        page=page,
        page_size=page_size,
        status=status,
        job_type=job_type,
        user_id=current_user.id,
        is_superuser=current_user.is_superuser,
    )
    return PageResponse(
        data=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=DataResponse[JobResponse])
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询任务详情"""
    service = JobService(db)
    job = service.get_job(job_id)
    if not job:
        raise NotFoundError("Job", job_id)
    ensure_job_access(db, current_user, job)
    return DataResponse(data=JobResponse.model_validate(job))


@router.post("/{job_id}/cancel", response_model=DataResponse[JobResponse])
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """请求取消任务"""
    service = JobService(db)
    job = service.get_job(job_id)
    if not job:
        raise NotFoundError("Job", job_id)
    ensure_job_access(db, current_user, job, write=True)
    previous_status = job.status
    task_id = service.get_celery_task_id(job)
    dispatch_mode = service.get_dispatch_metadata(job).get("mode")
    try:
        job = service.cancel_job(job_id)
    except ValueError as e:
        raise AppException(status_code=400, message=str(e)) from e

    if task_id:
        dispatcher = JobDispatcher.from_session(db)
        try:
            revoked = dispatcher.revoke(
                task_id,
                mode=str(dispatch_mode) if dispatch_mode else None,
                terminate=previous_status == "running",
            )
            service.record_revoke_result(
                job.id,
                task_id=task_id,
                revoked=revoked,
            )
        except JobDispatchError as exc:
            service.record_revoke_result(
                job.id,
                task_id=task_id,
                revoked=False,
                error_message=str(exc),
            )
    return DataResponse(data=JobResponse.model_validate(job))


@router.post("/{job_id}/retry", response_model=DataResponse[JobResponse])
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动重试任务"""
    service = JobService(db)
    old_job = service.get_job(job_id)
    if not old_job:
        raise NotFoundError("Job", job_id)
    ensure_job_access(db, current_user, old_job, write=True)
    # 创建新任务重试
    config = json.loads(old_job.request_snapshot) if old_job.request_snapshot else {}
    new_job = service.create_job(
        job_type=old_job.job_type,
        resource_id=old_job.resource_id,
        config=config,
        created_by=current_user.id,
        project_id=old_job.project_id,
        priority=old_job.priority,
        timeout_seconds=old_job.timeout_seconds,
        max_attempts=old_job.max_attempts,
    )
    new_job = _dispatch_queued_job(db, service, new_job)
    return DataResponse(data=JobResponse.model_validate(new_job))


@router.get("/{job_id}/events", response_model=DataResponse[list[JobEventResponse]])
def get_events(
    job_id: str,
    after_sequence: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """增量查询任务事件"""
    service = JobService(db)
    job = service.get_job(job_id)
    if not job:
        raise NotFoundError("Job", job_id)
    ensure_job_access(db, current_user, job)
    events = service.get_events(job_id, after_sequence)
    return DataResponse(data=[JobEventResponse.model_validate(e) for e in events])


@router.get("/{job_id}/artifacts", response_model=DataResponse[list[JobArtifactResponse]])
def get_artifacts(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询任务产物"""
    from app.models.job_artifact import JobArtifact

    service = JobService(db)
    job = service.get_job(job_id)
    if not job:
        raise NotFoundError("Job", job_id)
    ensure_job_access(db, current_user, job)
    artifacts = db.query(JobArtifact).filter(JobArtifact.job_id == job_id).all()
    return DataResponse(data=[JobArtifactResponse.model_validate(a) for a in artifacts])


@router.websocket("/{job_id}/stream")
async def job_stream(websocket: WebSocket, job_id: str):
    """WebSocket 实时事件流。

    通过查询参数 ?token=<JWT> 进行鉴权（浏览器 WebSocket 握手无法设置
    Authorization 头）。连接后每秒轮询数据库增量推送事件，任务进入终态后
    推送 done 消息并关闭连接。
    """
    from app.core.security import decode_access_token
    from app.database import SessionLocal
    from app.models.user import User

    # 从查询参数获取 token
    token = websocket.query_params.get("token")
    if not token:
        await websocket.accept()
        await websocket.close(code=4001, reason="缺少认证 token")
        return

    # 验证 token
    db = SessionLocal()
    try:
        try:
            payload = decode_access_token(token)
        except Exception:
            await websocket.accept()
            await websocket.close(code=4001, reason="无效的 token")
            return
        user_id = payload.get("sub")
        user = db.get(User, user_id) if user_id else None
        if not user or not user.is_active:
            await websocket.accept()
            await websocket.close(code=4001, reason="无效的用户")
            return
        job = JobService(db).get_job(job_id)
        if not job:
            await websocket.accept()
            await websocket.close(code=4004, reason="任务不存在")
            return
        try:
            ensure_job_access(db, user, job)
        except ForbiddenError:
            await websocket.accept()
            await websocket.close(code=4003, reason="无权访问该任务")
            return
    finally:
        db.close()

    await websocket.accept()
    try:
        last_sequence = 0
        while True:
            # 从数据库轮询事件（简化实现，生产环境用 Redis pub/sub）
            db = SessionLocal()
            try:
                service = JobService(db)
                events = service.get_events(job_id, last_sequence)
                for event in events:
                    await websocket.send_json({
                        "id": event.id,
                        "event_type": event.event_type,
                        "sequence": event.sequence,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    })
                    last_sequence = event.sequence

                # 检查任务是否结束
                job = service.get_job(job_id)
                if job and job.status in ("succeeded", "failed", "cancelled", "timed_out"):
                    await websocket.send_json({"event_type": "done", "status": job.status})
                    break
                if not job:
                    await websocket.send_json({"event_type": "done", "status": "not_found"})
                    break
            finally:
                db.close()

            await asyncio.sleep(1)  # 每秒轮询一次
    except WebSocketDisconnect:
        pass
