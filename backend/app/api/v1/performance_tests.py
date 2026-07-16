"""性能测试 API：压测场景 CRUD + 压测执行 + 结果查询 + 监控/SLA/实时/趋势."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.perf_metric import PerfMetric
from app.models.performance_result import PerformanceResult
from app.models.performance_test import PerformanceTest
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.schemas.performance_test import (
    PerformanceTestCreate,
    PerformanceTestUpdate,
)
from app.services import perf_realtime
from app.services.auth_service import get_current_user
from app.services.perf_runner import run_in_background
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# 序列化辅助函数
# ---------------------------------------------------------------------------

def _serialize_test(t: PerformanceTest) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "case_ids": t.case_ids,
        "config": t.config,
        "project_id": t.project_id,
        "status": t.status,
        "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _serialize_result(r: PerformanceResult) -> dict:
    return {
        "id": r.id,
        "test_id": r.test_id,
        "run_id": r.run_id,
        "total_requests": r.total_requests,
        "success_requests": r.success_requests,
        "fail_requests": r.fail_requests,
        "avg_response_time": r.avg_response_time,
        "min_response_time": r.min_response_time,
        "max_response_time": r.max_response_time,
        "p50": r.p50,
        "p90": r.p90,
        "p95": r.p95,
        "p99": r.p99,
        "rps": r.rps,
        "error_rate": r.error_rate,
        "duration": r.duration,
        "detail": r.detail,
        "sla_status": r.sla_status,
        "sla_details": r.sla_details,
        "mode": r.mode,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _ensure_case_ids_access(
    db: Session,
    user: User,
    case_ids: list[str],
    minimum_role: str,
    *,
    expected_project_id: str | None = None,
) -> list[TestCase]:
    cases: list[TestCase] = []
    for case_id in case_ids:
        case = db.get(TestCase, case_id)
        if not case:
            raise NotFoundError("测试用例", case_id)
        ensure_resource_role(
            db, user, case, minimum_role, owner_field=None
        )
        if (
            expected_project_id is not None
            and case.project_id != expected_project_id
        ):
            raise ValidationError(
                "Performance test cases must belong to the scenario project"
            )
        cases.append(case)
    return cases


# ---------------------------------------------------------------------------
# CRUD 端点（固定路径，必须在 /{test_id} 之前）
# ---------------------------------------------------------------------------

@router.get("", response_model=PageResponse[dict])
def list_performance_tests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """性能测试场景列表分页，支持按 project_id 筛选."""
    query = select(PerformanceTest)
    count_query = select(func.count()).select_from(PerformanceTest)
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query, PerformanceTest, current_user, owner_field=None
    )
    count_query = scope_project_resources(
        count_query, PerformanceTest, current_user, owner_field=None
    )

    if project_id is not None:
        query = query.where(PerformanceTest.project_id == project_id)
        count_query = count_query.where(PerformanceTest.project_id == project_id)

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(PerformanceTest.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_test(t) for t in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("", response_model=DataResponse[dict])
def create_performance_test(
    payload: PerformanceTestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建性能测试场景."""
    ensure_project_assignment(db, current_user, payload.project_id, "developer")
    _ensure_case_ids_access(
        db,
        current_user,
        payload.case_ids,
        "developer",
        expected_project_id=payload.project_id,
    )
    test = PerformanceTest(**payload.model_dump())
    db.add(test)
    db.commit()
    db.refresh(test)
    return DataResponse(data=_serialize_test(test))


@router.get("/results", response_model=PageResponse[dict])
def list_all_performance_results(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取所有压测结果列表（用于性能报告页）."""
    count_query = (
        select(func.count())
        .select_from(PerformanceResult)
        .join(
            PerformanceTest,
            PerformanceTest.id == PerformanceResult.test_id,
        )
    )
    query = select(PerformanceResult).join(
        PerformanceTest,
        PerformanceTest.id == PerformanceResult.test_id,
    )
    count_query = scope_project_resources(
        count_query, PerformanceTest, current_user, owner_field=None
    )
    query = scope_project_resources(
        query, PerformanceTest, current_user, owner_field=None
    )
    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(PerformanceResult.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_result(r) for r in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# 趋势对比（功能18）：固定路径，必须在 /{test_id} 之前
# ---------------------------------------------------------------------------

@router.get("/trends", response_model=DataResponse[dict])
def get_perf_trends(
    test_ids: str = Query(..., description="逗号分隔的压测场景 ID"),
    metric: str = Query("rps", description="对比指标：rps/p95/p99/error_rate/avg_response_time"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """趋势对比：返回多个压测场景的同一指标历史对比数据.

    返回 { metric, series: [{ test_id, test_name, points: [{result_id, created_at, value}] }] }
    """
    valid_metrics = {
        "rps": "rps", "p95": "p95", "p99": "p99",
        "error_rate": "error_rate", "avg_response_time": "avg_response_time",
        "p50": "p50", "p90": "p90",
    }
    col = valid_metrics.get(metric, "rps")

    ids = [tid.strip() for tid in test_ids.split(",") if tid.strip()]
    series: list[dict] = []
    for tid in ids:
        test = db.get(PerformanceTest, tid)
        if not test:
            raise NotFoundError("性能测试场景", tid)
        ensure_resource_role(
            db, current_user, test, "viewer", owner_field=None
        )
        test_name = test.name
        rows = (
            db.execute(
                select(PerformanceResult)
                .where(PerformanceResult.test_id == tid)
                .order_by(PerformanceResult.created_at.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        points = [
            {
                "result_id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "value": float(getattr(r, col) or 0.0),
            }
            for r in rows
        ]
        series.append({"test_id": tid, "test_name": test_name, "points": points})
    return DataResponse(data={"metric": col, "series": series})


# ---------------------------------------------------------------------------
# 单个场景操作（含路径参数 /{test_id}）
# ---------------------------------------------------------------------------

@router.get("/{test_id}", response_model=DataResponse[dict])
def get_performance_test(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个性能测试场景."""
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "viewer", owner_field=None)
    return DataResponse(data=_serialize_test(test))


@router.put("/{test_id}", response_model=DataResponse[dict])
def update_performance_test(
    test_id: str,
    payload: PerformanceTestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新性能测试场景."""
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(
        db, current_user, test, "developer", owner_field=None
    )
    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data:
        ensure_resource_role(
            db, current_user, test, "admin", owner_field=None
        )
    target_project_id = update_data.get("project_id", test.project_id)
    if target_project_id != test.project_id:
        ensure_resource_role(db, current_user, test, "admin", owner_field=None)
        ensure_project_assignment(
            db, current_user, target_project_id, "admin"
        )
    target_case_ids = update_data.get("case_ids", test.case_ids or [])
    if "case_ids" in update_data or target_project_id != test.project_id:
        _ensure_case_ids_access(
            db,
            current_user,
            target_case_ids,
            "developer",
            expected_project_id=target_project_id,
        )
    for field, value in update_data.items():
        setattr(test, field, value)
    db.commit()
    db.refresh(test)
    return DataResponse(data=_serialize_test(test))


@router.delete("/{test_id}", response_model=DataResponse[dict])
def delete_performance_test(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除性能测试场景（级联删除结果）."""
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "admin", owner_field=None)
    db.delete(test)
    db.commit()
    return DataResponse(data={"id": test_id, "deleted": True})


@router.post("/{test_id}/run", response_model=DataResponse[dict])
def run_performance_test(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """异步启动性能测试（后台执行），立即返回 run_id 与 running 状态.

    实际执行在后台守护线程中进行，支持功能14 多模式、功能15 服务器监控、
    功能16 SLA 评估、功能17 实时快照。前端通过 GET /{test_id}/realtime 轮询进度，
    完成后通过 /{test_id}/results 获取最终结果。
    """
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "tester", owner_field=None)

    # 若该场景已有压测在运行，拒绝重复启动
    existing = perf_realtime.get(test_id)
    if existing and existing.get("status") == "running":
        return DataResponse(data={
            "test_id": test_id,
            "run_id": existing.get("run_id"),
            "status": "running",
            "message": "该场景已有压测正在运行。",
        })

    run_id = run_in_background(test_id)
    return DataResponse(data={
        "test_id": test_id,
        "run_id": run_id,
        "status": "running",
    })


@router.get("/{test_id}/realtime", response_model=DataResponse[dict])
def get_realtime(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取压测实时指标快照（功能17，前端每 2 秒轮询）.

    返回 { status, run_id, result_id, error, latest, snapshots }。
    若无运行中压测且已完成，status 为 completed 并附带 result_id。
    """
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "viewer", owner_field=None)

    data = perf_realtime.get(test_id)
    if data is None:
        # 没有内存记录，回退为场景当前状态
        return DataResponse(data={
            "test_id": test_id,
            "status": test.status,
            "run_id": None,
            "result_id": None,
            "error": None,
            "latest": None,
            "snapshots": [],
        })
    snapshots = data.get("snapshots") or []
    latest = snapshots[-1] if snapshots else None
    return DataResponse(data={
        "test_id": test_id,
        "status": data.get("status"),
        "run_id": data.get("run_id"),
        "result_id": data.get("result_id"),
        "error": data.get("error"),
        "latest": latest,
        "snapshots": snapshots,
    })


@router.delete("/{test_id}/realtime", response_model=DataResponse[dict])
def clear_realtime(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清理某压测的实时内存存储（压测结束后前端可调用释放）."""
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "admin", owner_field=None)
    perf_realtime.clear(test_id)
    return DataResponse(data={"test_id": test_id, "cleared": True})


@router.get("/{test_id}/metrics", response_model=DataResponse[dict])
def get_server_metrics(
    test_id: str,
    result_id: str | None = Query(None, description="按结果 ID 筛选；不传则取最近一次结果"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取压测期间的服务器监控指标时间序列（功能15）."""
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "viewer", owner_field=None)

    query = select(PerfMetric).where(PerfMetric.test_id == test_id)
    if result_id:
        query = query.where(PerfMetric.result_id == result_id)
    else:
        # 取该场景最近一次结果的指标
        latest_result = (
            db.execute(
                select(PerformanceResult.id)
                .where(PerformanceResult.test_id == test_id)
                .order_by(PerformanceResult.created_at.desc())
                .limit(1)
            )
            .scalar_one_or_none()
        )
        if not latest_result:
            return DataResponse(data={"test_id": test_id, "result_id": None, "metrics": []})
        query = query.where(PerfMetric.result_id == latest_result)
        result_id = latest_result

    rows = (
        db.execute(query.order_by(PerfMetric.elapsed.asc()))
        .scalars()
        .all()
    )
    metrics = [
        {
            "elapsed": m.elapsed,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "cpu": m.cpu,
            "memory": m.memory,
            "disk_read": m.disk_read,
            "disk_write": m.disk_write,
            "net_sent": m.net_sent,
            "net_recv": m.net_recv,
        }
        for m in rows
    ]
    return DataResponse(data={"test_id": test_id, "result_id": result_id, "metrics": metrics})


@router.get("/{test_id}/history", response_model=PageResponse[dict])
def get_test_history(
    test_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取同一压测场景的历史结果列表（功能18，用于趋势对比）."""
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "viewer", owner_field=None)

    count_query = (
        select(func.count())
        .select_from(PerformanceResult)
        .where(PerformanceResult.test_id == test_id)
    )
    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            select(PerformanceResult)
            .where(PerformanceResult.test_id == test_id)
            .order_by(PerformanceResult.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_result(r) for r in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.get("/{test_id}/results/{result_id}/sla", response_model=DataResponse[dict])
def get_sla_detail(
    test_id: str,
    result_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取某次压测结果的 SLA 评估详情（功能16）."""
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "viewer", owner_field=None)
    result = db.get(PerformanceResult, result_id)
    if not result or result.test_id != test_id:
        raise NotFoundError("压测结果", result_id)
    return DataResponse(data={
        "result_id": result_id,
        "test_id": test_id,
        "sla_status": result.sla_status,
        "sla_details": result.sla_details,
        "p95": result.p95,
        "error_rate": result.error_rate,
        "rps": result.rps,
    })


@router.get("/{test_id}/results", response_model=PageResponse[dict])
def list_performance_results(
    test_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取某压测场景的结果列表."""
    test = db.get(PerformanceTest, test_id)
    if not test:
        raise NotFoundError("性能测试场景", test_id)
    ensure_resource_role(db, current_user, test, "viewer", owner_field=None)

    count_query = (
        select(func.count())
        .select_from(PerformanceResult)
        .where(PerformanceResult.test_id == test_id)
    )
    total = db.execute(count_query).scalar_one()

    items = (
        db.execute(
            select(PerformanceResult)
            .where(PerformanceResult.test_id == test_id)
            .order_by(PerformanceResult.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_result(r) for r in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)
