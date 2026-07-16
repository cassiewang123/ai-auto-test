"""UI 测试套件管理 API：CRUD + 批量执行 + 执行记录查询."""
from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.ui_test_case import UiTestCase
from app.models.ui_test_record import UiTestRecord
from app.models.ui_test_suite import UiTestSuite, UiTestSuiteRun
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class SuiteCreate(BaseModel):
    """创建 UI 测试套件."""
    name: str
    description: str | None = None
    project_id: str | None = None
    case_ids: list[str] = []
    is_active: bool = True
    execution_mode: str = "sequential"  # sequential / parallel
    max_workers: int = 4
    retry_enabled: bool = True  # 是否启用失败重试


class SuiteUpdate(BaseModel):
    """更新 UI 测试套件."""
    name: str | None = None
    description: str | None = None
    project_id: str | None = None
    case_ids: list[str] | None = None
    is_active: bool | None = None
    execution_mode: str | None = None
    max_workers: int | None = None
    retry_enabled: bool | None = None


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _serialize_suite(s: UiTestSuite, case_count: int | None = None) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "project_id": s.project_id,
        "case_ids": s.case_ids or [],
        "case_count": case_count if case_count is not None else len(s.case_ids or []),
        "is_active": s.is_active,
        "execution_mode": s.execution_mode or "sequential",
        "max_workers": s.max_workers if s.max_workers is not None else 4,
        "retry_enabled": s.retry_enabled if s.retry_enabled is not None else True,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_suite_run(r: UiTestSuiteRun) -> dict:
    return {
        "id": r.id,
        "suite_id": r.suite_id,
        "suite_name": r.suite_name,
        "project_id": r.project_id,
        "total": r.total,
        "passed": r.passed,
        "failed": r.failed,
        "duration": r.duration,
        "status": r.status,
        "record_ids": r.record_ids or [],
        "triggered_by": r.triggered_by,
        "execution_mode": r.execution_mode or "sequential",
        "max_workers": r.max_workers if r.max_workers is not None else 1,
        "parallel_duration": r.parallel_duration,
        "retry_enabled": r.retry_enabled if r.retry_enabled is not None else True,
        "total_retries": r.total_retries if r.total_retries is not None else 0,
        "retried_cases": r.retried_cases or [],
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


def _ensure_case_ids_access(
    db: Session,
    user: User,
    case_ids: list[str],
    minimum_role: str,
    *,
    expected_project_id: str | None = None,
    allow_missing: bool = False,
) -> list[UiTestCase]:
    cases: list[UiTestCase] = []
    for case_id in case_ids:
        case = db.get(UiTestCase, case_id)
        if not case:
            if allow_missing:
                continue
            raise NotFoundError("UI 测试用例", case_id)
        ensure_resource_role(
            db, user, case, minimum_role, owner_field=None
        )
        if (
            expected_project_id is not None
            and case.project_id != expected_project_id
        ):
            raise ValidationError("Suite cases must belong to the suite project")
        cases.append(case)
    return cases


# ---------------------------------------------------------------------------
# CRUD 端点
# ---------------------------------------------------------------------------

@router.get("", response_model=PageResponse[dict])
def list_suites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """UI 测试套件列表分页."""
    query = select(UiTestSuite)
    count_query = select(func.count()).select_from(UiTestSuite)
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query, UiTestSuite, current_user, owner_field=None
    )
    count_query = scope_project_resources(
        count_query, UiTestSuite, current_user, owner_field=None
    )

    if project_id is not None:
        query = query.where(UiTestSuite.project_id == project_id)
        count_query = count_query.where(UiTestSuite.project_id == project_id)

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(UiTestSuite.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_suite(s) for s in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("", response_model=DataResponse[dict])
def create_suite(
    payload: SuiteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建 UI 测试套件."""
    ensure_project_assignment(db, current_user, payload.project_id, "developer")
    _ensure_case_ids_access(
        db,
        current_user,
        payload.case_ids,
        "developer",
        expected_project_id=payload.project_id,
    )
    suite = UiTestSuite(**payload.model_dump())
    db.add(suite)
    db.commit()
    db.refresh(suite)
    return DataResponse(data=_serialize_suite(suite))


@router.get("/{suite_id}", response_model=DataResponse[dict])
def get_suite(
    suite_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个 UI 测试套件详情（含用例标题列表）."""
    suite = db.get(UiTestSuite, suite_id)
    if not suite:
        raise NotFoundError("UI 测试套件", suite_id)
    ensure_resource_role(
        db, current_user, suite, "viewer", owner_field=None
    )
    data = _serialize_suite(suite)
    # 关联查询用例标题
    cases = []
    if suite.case_ids:
        _ensure_case_ids_access(
            db, current_user, suite.case_ids, "viewer", allow_missing=True
        )
        rows = db.execute(
            select(UiTestCase.id, UiTestCase.title).where(
                UiTestCase.id.in_(suite.case_ids)
            )
        ).all()
        case_map = {row.id: row.title for row in rows}
        cases = [
            {"id": cid, "title": case_map.get(cid, "(已删除)")}
            for cid in suite.case_ids
        ]
    data["cases"] = cases
    return DataResponse(data=data)


@router.put("/{suite_id}", response_model=DataResponse[dict])
def update_suite(
    suite_id: str,
    payload: SuiteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 UI 测试套件."""
    suite = db.get(UiTestSuite, suite_id)
    if not suite:
        raise NotFoundError("UI 测试套件", suite_id)
    ensure_resource_role(
        db, current_user, suite, "developer", owner_field=None
    )
    update_data = payload.model_dump(exclude_unset=True)
    target_project_id = update_data.get("project_id", suite.project_id)
    if target_project_id != suite.project_id:
        ensure_resource_role(
            db, current_user, suite, "admin", owner_field=None
        )
        ensure_project_assignment(
            db, current_user, target_project_id, "admin"
        )
    target_case_ids = update_data.get("case_ids", suite.case_ids or [])
    if "case_ids" in update_data or target_project_id != suite.project_id:
        _ensure_case_ids_access(
            db,
            current_user,
            target_case_ids,
            "developer",
            expected_project_id=target_project_id,
        )
    for field, value in update_data.items():
        setattr(suite, field, value)
    db.commit()
    db.refresh(suite)
    return DataResponse(data=_serialize_suite(suite))


@router.delete("/{suite_id}", response_model=DataResponse[dict])
def delete_suite(
    suite_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 UI 测试套件."""
    suite = db.get(UiTestSuite, suite_id)
    if not suite:
        raise NotFoundError("UI 测试套件", suite_id)
    ensure_resource_role(db, current_user, suite, "admin", owner_field=None)
    db.delete(suite)
    db.commit()
    return DataResponse(data={"id": suite_id, "deleted": True})


# ---------------------------------------------------------------------------
# 批量执行套件内所有用例
# ---------------------------------------------------------------------------

def _execute_single_case(
    case: UiTestCase,
    steps: list[dict],
    retry_count: int = 0,
    retry_interval: float = 2.0,
) -> dict:
    """执行单个 UI 测试用例，返回结果字典（线程安全，不操作数据库）.

    步骤组需在主线程预展开后传入；本函数以 db=None 调用执行引擎，
    确保线程内不会访问数据库。Playwright 的 sync_playwright 在每次调用
    时通过上下文管理器创建独立实例，因此并行执行时每个线程拥有独立的
    浏览器实例，互不干扰。

    支持失败自动重试：retry_count > 0 时，失败后等待 retry_interval 秒重试，
    任意一次成功即停止。

    返回字段：case_id / case_title / project_id / url / browser_type /
    status / total_steps / passed_steps / failed_steps / duration /
    error / step_results / screenshots / started_at / retry_attempts / final_attempt
    """
    from app.services.ui.execution_service import _execute_with_retry

    started_at = datetime.now()
    case_start = time.time()
    result, retry_attempts, final_attempt_num = _execute_with_retry(
        url=case.url,
        browser_type=case.browser_type or "chrome",
        steps=steps,
        retry_count=retry_count,
        retry_interval=retry_interval,
        db=None,  # 步骤已预展开，线程内不再访问数据库
    )
    case_duration = round(time.time() - case_start, 3)

    return {
        "case_id": case.id,
        "case_title": case.title,
        "project_id": case.project_id,
        "url": case.url,
        "browser_type": case.browser_type or "chrome",
        "status": result["status"],
        "total_steps": result["total_steps"],
        "passed_steps": result["passed_steps"],
        "failed_steps": result["failed_steps"],
        "duration": case_duration,
        "error": result["error"],
        "step_results": result["steps"],
        "screenshots": result.get("screenshots", []),
        # 真实执行起始时间（并行模式下各用例起始时间不同，用于时间线展示）
        "started_at": started_at,
        "retry_attempts": retry_attempts,
        "final_attempt": final_attempt_num,
    }


def _build_record_from_result(result: dict, suite_name: str) -> UiTestRecord:
    """根据 _execute_single_case 返回的结果字典构造 UiTestRecord（主线程调用）."""
    return UiTestRecord(
        case_id=result["case_id"],
        case_title=result["case_title"],
        project_id=result["project_id"],
        url=result["url"],
        browser_type=result["browser_type"],
        status=result["status"],
        total_steps=result["total_steps"],
        passed_steps=result["passed_steps"],
        failed_steps=result["failed_steps"],
        duration=result["duration"],
        error=result["error"],
        step_results=result["step_results"],
        retry_attempts=result.get("retry_attempts", []),
        final_attempt=result.get("final_attempt", 1),
        triggered_by=f"suite:{suite_name}",
        # 显式覆盖 executed_at，记录真实执行起始时间（而非入库时间）
        executed_at=result["started_at"],
    )


@router.post("/{suite_id}/run", response_model=DataResponse[dict])
def run_suite(
    suite_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量执行套件内所有用例.

    复用 ui_test_cases 模块的 Playwright 执行引擎，支持两种执行模式：
    - sequential：顺序执行（保持原有逻辑）
    - parallel：并行执行，使用 ThreadPoolExecutor 并发运行多个用例

    并行执行注意事项：
    - 步骤组（step_group）在主线程预展开，避免线程内访问数据库
    - 每个线程内 _execute_steps_with_playwright 以 db=None 调用，
      并通过 sync_playwright 创建独立的 Playwright 实例
    - 线程内不操作数据库，仅收集结果；所有 UiTestRecord 在主线程统一写入
    - 通过 as_completed 收集结果，保证某用例失败不影响其他用例
    """
    from app.services.ui.execution_service import _expand_step_groups

    suite = db.get(UiTestSuite, suite_id)
    if not suite:
        raise NotFoundError("UI 测试套件", suite_id)
    ensure_resource_role(db, current_user, suite, "tester", owner_field=None)

    case_ids = suite.case_ids or []
    _ensure_case_ids_access(
        db, current_user, case_ids, "tester", allow_missing=True
    )
    # 查询套件内所有用例
    cases = (
        db.execute(
            select(UiTestCase).where(
                UiTestCase.id.in_(case_ids), UiTestCase.is_active.is_(True)
            )
        )
        .scalars()
        .all()
    ) if case_ids else []

    execution_mode = suite.execution_mode or "sequential"
    max_workers = suite.max_workers or 4
    # 是否启用失败重试：开启后套件内用例按各自 retry_count 自动重试
    retry_enabled = suite.retry_enabled if suite.retry_enabled is not None else True

    # 主线程预展开步骤组（step_group），避免线程内访问数据库
    case_steps_pairs = [
        (case, _expand_step_groups(case.steps or [], db)) for case in cases
    ]

    # 创建套件执行记录
    suite_run = UiTestSuiteRun(
        suite_id=suite.id,
        suite_name=suite.name,
        project_id=suite.project_id,
        total=len(cases),
        passed=0,
        failed=0,
        status="running",
        record_ids=[],
        triggered_by="manual",
        execution_mode=execution_mode,
        max_workers=max_workers if execution_mode == "parallel" else 1,
        retry_enabled=retry_enabled,
    )
    db.add(suite_run)
    db.commit()
    db.refresh(suite_run)

    start_time = time.time()
    results: list[dict] = []

    if execution_mode == "parallel" and len(case_steps_pairs) > 0:
        # 并行执行：每个线程独立 Playwright 实例，线程内不操作数据库
        from concurrent.futures import ThreadPoolExecutor, as_completed

        workers = min(max_workers, len(case_steps_pairs))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_case = {
                executor.submit(
                    _execute_single_case,
                    case,
                    steps,
                    # 启用重试时使用用例自身的重试配置，否则传 0 不重试
                    case.retry_count if retry_enabled else 0,
                    case.retry_interval if case.retry_interval is not None else 2.0,
                ): case
                for case, steps in case_steps_pairs
            }
            for future in as_completed(future_to_case):
                case = future_to_case[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    # 单个用例异常不应中断整体执行
                    results.append({
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
                        "error": f"并行执行异常: {e}",
                        "step_results": [],
                        "screenshots": [],
                        "started_at": datetime.now(),
                        "retry_attempts": [],
                        "final_attempt": 1,
                    })
    else:
        # 顺序执行（保持现有逻辑）
        for case, steps in case_steps_pairs:
            results.append(_execute_single_case(
                case,
                steps,
                retry_count=case.retry_count if retry_enabled else 0,
                retry_interval=case.retry_interval if case.retry_interval is not None else 2.0,
            ))

    duration = round(time.time() - start_time, 3)

    # 主线程统一写入所有用例执行记录
    record_ids: list[str] = []
    passed_count = 0
    failed_count = 0
    serial_estimate = 0.0  # 串行预估总耗时（各用例耗时之和）
    total_retries = 0  # 总重试次数（所有用例额外尝试次数之和）
    retried_cases: list[dict] = []  # 重试过的用例列表

    for result in results:
        serial_estimate += result["duration"]
        record = _build_record_from_result(result, suite.name)
        db.add(record)
        db.commit()
        db.refresh(record)
        record_ids.append(record.id)

        if result["status"] == "passed":
            passed_count += 1
        else:
            failed_count += 1

        # 统计重试信息：有多次尝试说明发生过重试
        attempts = result.get("retry_attempts") or []
        if len(attempts) > 1:
            # 额外尝试次数 = 总尝试次数 - 1（首次不算重试）
            total_retries += len(attempts) - 1
            retried_cases.append({
                "case_id": result["case_id"],
                "case_title": result["case_title"],
                "attempts": len(attempts),
                "final_status": result["status"],
            })

    suite_run.passed = passed_count
    suite_run.failed = failed_count
    suite_run.duration = duration
    suite_run.record_ids = record_ids
    suite_run.status = "completed"
    suite_run.finished_at = datetime.now()
    suite_run.total_retries = total_retries
    suite_run.retried_cases = retried_cases
    # 并行模式记录串行预估耗时，用于前端计算加速比
    if execution_mode == "parallel":
        suite_run.parallel_duration = round(serial_estimate, 3)
    db.commit()
    db.refresh(suite_run)

    return DataResponse(data={
        "run_id": suite_run.id,
        "suite_id": suite.id,
        "suite_name": suite.name,
        "total": suite_run.total,
        "passed": passed_count,
        "failed": failed_count,
        "duration": duration,
        "execution_mode": execution_mode,
        "max_workers": suite_run.max_workers,
        "parallel_duration": suite_run.parallel_duration,
        "retry_enabled": retry_enabled,
        "total_retries": total_retries,
        "retried_cases": retried_cases,
        "record_ids": record_ids,
        "status": "completed",
    })


# ---------------------------------------------------------------------------
# 套件执行记录查询
# ---------------------------------------------------------------------------

@router.get("/{suite_id}/runs", response_model=DataResponse[list])
def list_suite_runs(
    suite_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询某套件的执行记录列表."""
    suite = db.get(UiTestSuite, suite_id)
    if not suite:
        raise NotFoundError("UI 测试套件", suite_id)
    ensure_resource_role(
        db, current_user, suite, "viewer", owner_field=None
    )
    items = (
        db.execute(
            select(UiTestSuiteRun)
            .where(UiTestSuiteRun.suite_id == suite_id)
            .order_by(UiTestSuiteRun.started_at.desc())
        )
        .scalars()
        .all()
    )
    data = [_serialize_suite_run(r) for r in items]
    return DataResponse(data=data)


@router.get("/runs/{run_id}", response_model=DataResponse[dict])
def get_suite_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单条套件执行记录详情（含关联的用例执行记录）."""
    run = db.get(UiTestSuiteRun, run_id)
    if not run:
        raise NotFoundError("套件执行记录", run_id)
    ensure_resource_role(db, current_user, run, "viewer", owner_field=None)
    data = _serialize_suite_run(run)
    # 关联查询每条用例执行记录
    records = []
    if run.record_ids:
        rows = (
            db.execute(
                select(UiTestRecord).where(UiTestRecord.id.in_(run.record_ids))
            )
            .scalars()
            .all()
        )
        record_map = {r.id: r for r in rows}
        for rid in run.record_ids:
            r = record_map.get(rid)
            if r:
                records.append({
                    "id": r.id,
                    "case_id": r.case_id,
                    "case_title": r.case_title,
                    "status": r.status,
                    "total_steps": r.total_steps,
                    "passed_steps": r.passed_steps,
                    "failed_steps": r.failed_steps,
                    "duration": r.duration,
                    "error": r.error,
                    "retry_attempts": r.retry_attempts or [],
                    "final_attempt": r.final_attempt if r.final_attempt is not None else 1,
                    "executed_at": r.executed_at.isoformat() if r.executed_at else None,
                })
    data["records"] = records
    return DataResponse(data=data)
