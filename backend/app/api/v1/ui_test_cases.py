"""UI 测试用例 CRUD API.

REF-02: 执行引擎与录屏逻辑已拆分至 ``app/services/ui/`` 下：
- ``services/ui/execution_service.py``：Playwright 执行引擎 + 健壮操作辅助
- ``services/ui/recording_service.py``：浏览器录屏会话管理
- ``services/ui/artifact_service.py``：文件路径校验与 Artifact 解析（SEC-06）

本模块仅保留 CRUD 端点、序列化与路由定义。
"""
from __future__ import annotations

import time
import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.database import get_db
from app.models.ui_test_case import UiTestCase
from app.models.ui_test_record import UiTestRecord
from app.models.user import User
from app.models.visual_baseline import VisualBaseline, VisualDiffResult
from app.schemas.common import DataResponse, PageResponse
from app.schemas.ui_test_case import (
    ExtractStepsRequest,
    StartRecordingRequest,
    UiTestCaseCreate,
    UiTestCaseUpdate,
)
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)
from app.services.ui.execution_service import execute_ui_case
from app.services.ui.recording_service import (
    get_recording_events,
    save_recording_as_case,
    start_recording,
    stop_recording,
)

router = APIRouter()
_recording_owners: dict[str, str] = {}


# ---------------------------------------------------------------------------
# 序列化辅助函数
# ---------------------------------------------------------------------------

def _serialize_case(c: UiTestCase) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "url": c.url,
        "browser_type": c.browser_type,
        "steps": c.steps,
        "project_id": c.project_id,
        "is_active": c.is_active,
        "retry_count": c.retry_count if c.retry_count is not None else 0,
        "retry_interval": c.retry_interval if c.retry_interval is not None else 2.0,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _ensure_recording_owner(session_id: str, user: User) -> None:
    owner_id = _recording_owners.get(session_id)
    if user.is_superuser:
        return
    if owner_id is None:
        raise NotFoundError("录屏会话", session_id)
    if owner_id != user.id:
        raise ForbiddenError("Recording session access denied")


# ---------------------------------------------------------------------------
# CRUD 端点
# ---------------------------------------------------------------------------

@router.get("", response_model=PageResponse[dict])
def list_ui_test_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    title_search: str | None = Query(None, description="按标题模糊搜索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """UI 测试用例列表分页，支持按 project_id、标题筛选."""
    query = select(UiTestCase)
    count_query = select(func.count()).select_from(UiTestCase)
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query, UiTestCase, current_user, owner_field=None
    )
    count_query = scope_project_resources(
        count_query, UiTestCase, current_user, owner_field=None
    )

    if project_id is not None:
        query = query.where(UiTestCase.project_id == project_id)
        count_query = count_query.where(UiTestCase.project_id == project_id)
    if title_search:
        query = query.where(UiTestCase.title.like(f"%{title_search}%"))
        count_query = count_query.where(UiTestCase.title.like(f"%{title_search}%"))

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(UiTestCase.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_case(c) for c in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("", response_model=DataResponse[dict])
def create_ui_test_case(
    payload: UiTestCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建 UI 测试用例."""
    ensure_project_assignment(db, current_user, payload.project_id, "developer")
    case = UiTestCase(**payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return DataResponse(data=_serialize_case(case))


@router.get("/{case_id}", response_model=DataResponse[dict])
def get_ui_test_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个 UI 测试用例."""
    case = db.get(UiTestCase, case_id)
    if not case:
        raise NotFoundError("UI 测试用例", case_id)
    ensure_resource_role(db, current_user, case, "viewer", owner_field=None)
    return DataResponse(data=_serialize_case(case))


@router.put("/{case_id}", response_model=DataResponse[dict])
def update_ui_test_case(
    case_id: str,
    payload: UiTestCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 UI 测试用例."""
    case = db.get(UiTestCase, case_id)
    if not case:
        raise NotFoundError("UI 测试用例", case_id)
    ensure_resource_role(db, current_user, case, "developer", owner_field=None)
    update_data = payload.model_dump(exclude_unset=True)
    if "project_id" in update_data and update_data["project_id"] != case.project_id:
        ensure_resource_role(db, current_user, case, "admin", owner_field=None)
        ensure_project_assignment(
            db, current_user, update_data["project_id"], "admin"
        )
    for field, value in update_data.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return DataResponse(data=_serialize_case(case))


@router.delete("/{case_id}", response_model=DataResponse[dict])
def delete_ui_test_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 UI 测试用例."""
    case = db.get(UiTestCase, case_id)
    if not case:
        raise NotFoundError("UI 测试用例", case_id)
    ensure_resource_role(db, current_user, case, "admin", owner_field=None)
    db.delete(case)
    db.commit()
    return DataResponse(data={"id": case_id, "deleted": True})


@router.post("/{case_id}/extract-steps", response_model=DataResponse[dict])
def extract_steps_from_case(
    case_id: str,
    payload: ExtractStepsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从现有用例的指定步骤范围创建可复用步骤组.

    将用例 steps 中 [start_index, end_index) 范围内的步骤提取为一个新的 StepLibrary
    步骤组，便于在其他用例中复用。
    """
    from app.models.step_library import StepLibrary

    case = db.get(UiTestCase, case_id)
    if not case:
        raise NotFoundError("UI 测试用例", case_id)
    ensure_resource_role(db, current_user, case, "developer", owner_field=None)
    target_project_id = payload.project_id or case.project_id
    ensure_project_assignment(
        db, current_user, target_project_id, "developer"
    )

    all_steps = case.steps or []
    start = max(payload.start_index, 0)
    end = payload.end_index if payload.end_index is not None else len(all_steps)
    if end > len(all_steps):
        end = len(all_steps)
    if start >= end:
        raise ValueError("start_index 必须小于 end_index，且在用例步骤范围内")

    extracted = [dict(s) for s in all_steps[start:end]]

    sg = StepLibrary(
        id=str(_uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        project_id=target_project_id,
        steps=extracted,
        tags=[],
        usage_count=0,
    )
    db.add(sg)
    db.commit()
    db.refresh(sg)

    return DataResponse(
        data={
            "id": sg.id,
            "name": sg.name,
            "description": sg.description,
            "project_id": sg.project_id,
            "steps": sg.steps,
            "step_count": len(sg.steps or []),
            "tags": sg.tags or [],
            "usage_count": sg.usage_count or 0,
            "source_case_id": case.id,
            "source_case_title": case.title,
            "extracted_range": [start, end],
            "created_at": sg.created_at.isoformat() if sg.created_at else None,
            "updated_at": sg.updated_at.isoformat() if sg.updated_at else None,
        }
    )


@router.post("/{case_id}/run", response_model=DataResponse[dict])
def run_ui_test_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行 UI 测试用例（使用 Playwright 浏览器自动化引擎）.

    支持的步骤动作：
    - navigate: 导航到 URL
    - click: 点击元素
    - input: 输入文本
    - assert: 断言元素文本包含期望值
    - wait: 等待指定秒数
    - screenshot: 截图
    - select: 选择下拉选项
    - press: 按键
    - hover: 悬停元素
    - drag: 拖拽元素（source + target）
    - scroll: 滚动（direction + amount）
    - upload: 上传文件（file_path 或 artifact_id，SEC-06）
    - download: 下载文件（save_path 或 artifact_id，SEC-06）
    """
    case = db.get(UiTestCase, case_id)
    if not case:
        raise NotFoundError("UI 测试用例", case_id)
    ensure_resource_role(db, current_user, case, "tester", owner_field=None)

    steps = case.steps or []
    start_time = time.time()

    # 失败自动重试：在执行引擎外层包裹重试逻辑（委托给 execution_service）
    result, retry_attempts, final_attempt_num = execute_ui_case(
        url=case.url,
        browser_type=case.browser_type or "chrome",
        steps=steps,
        retry_count=case.retry_count or 0,
        retry_interval=case.retry_interval if case.retry_interval is not None else 2.0,
        db=db,
    )

    duration = round(time.time() - start_time, 3)

    # 保存执行记录到 ui_test_records 表
    record = UiTestRecord(
        case_id=case.id,
        case_title=case.title,
        project_id=case.project_id,
        url=case.url,
        browser_type=case.browser_type or "chrome",
        status=result["status"],
        total_steps=result["total_steps"],
        passed_steps=result["passed_steps"],
        failed_steps=result["failed_steps"],
        duration=duration,
        error=result["error"],
        step_results=result["steps"],
        retry_attempts=retry_attempts,
        final_attempt=final_attempt_num,
        triggered_by="manual",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # ---- 视觉回归对比：若该用例存在基线，则与最终截图对比 ----
    visual_diff = None
    try:
        # 取该用例最近一条基线
        baseline = db.execute(
            select(VisualBaseline)
            .where(VisualBaseline.ui_test_case_id == case.id)
            .order_by(VisualBaseline.created_at.desc())
            .limit(1)
        ).scalars().first()
        if baseline and result.get("screenshots"):
            # 用最后一张截图（最终状态）与基线对比
            from app.api.v1.visual_regression import compare_images
            current_b64 = result["screenshots"][-1]
            diff_score, diff_image = compare_images(baseline.baseline_image, current_b64)
            passed = diff_score <= baseline.threshold
            diff_result = VisualDiffResult(
                ui_test_record_id=record.id,
                baseline_id=baseline.id,
                diff_score=diff_score,
                diff_image=diff_image or None,
                passed=passed,
            )
            db.add(diff_result)
            db.commit()
            db.refresh(diff_result)
            visual_diff = {
                "diff_id": diff_result.id,
                "baseline_id": baseline.id,
                "baseline_name": baseline.name,
                "diff_score": diff_score,
                "threshold": baseline.threshold,
                "passed": passed,
                "diff_image": diff_image,
            }
    except Exception as e:
        # 视觉对比失败不影响主流程，仅记录错误
        import logging
        logging.getLogger(__name__).warning(f"视觉回归对比失败: {e}")

    return DataResponse(data={
        "case_id": case.id,
        "record_id": record.id,
        "title": case.title,
        "url": case.url,
        "browser_type": case.browser_type,
        "status": result["status"],
        "total_steps": result["total_steps"],
        "passed_steps": result["passed_steps"],
        "failed_steps": result["failed_steps"],
        "error": result["error"],
        "duration": duration,
        "steps": result["steps"],
        "screenshots": result["screenshots"],
        "final_url": result["final_url"],
        "visual_diff": visual_diff,
        "retry_attempts": retry_attempts,
        "final_attempt": final_attempt_num,
        "executed_at": datetime.now().isoformat(),
    })


# ---------------------------------------------------------------------------
# 录屏端点：委托给 services/ui/recording_service.py
# ---------------------------------------------------------------------------

@router.post("/start-recording", response_model=DataResponse[dict])
def start_recording_endpoint(
    req: StartRecordingRequest,
    current_user: User = Depends(get_current_user),
):
    """启动浏览器录屏会话.

    会以有头模式打开 Playwright 浏览器，注入录屏脚本捕获用户操作。
    返回 session_id 用于后续轮询事件和停止录制。
    """
    data = start_recording(req.url, req.browser_type)
    _recording_owners[data["session_id"]] = current_user.id
    return DataResponse(data=data)


@router.get("/recording/{session_id}/events", response_model=DataResponse[dict])
def get_recording_events_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取录屏会话的实时事件（前端轮询调用）."""
    _ensure_recording_owner(session_id, current_user)
    return DataResponse(data=get_recording_events(session_id))


@router.post("/stop-recording/{session_id}", response_model=DataResponse[dict])
def stop_recording_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """停止录屏，将捕获的事件转换为 UI 测试步骤并返回."""
    _ensure_recording_owner(session_id, current_user)
    data = stop_recording(session_id)
    _recording_owners.pop(session_id, None)
    return DataResponse(data=data)


@router.post("/recording/{session_id}/save", response_model=DataResponse[dict])
def save_recording_as_case_endpoint(
    session_id: str,
    title: str = Query(..., description="用例标题"),
    project_id: str | None = Query(None, description="项目ID"),
    url: str | None = Query(None, description="起始URL（默认使用录制时的URL）"),
    browser_type: str = Query("chrome", description="浏览器类型"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """停止录制并保存为 UI 测试用例."""
    _ensure_recording_owner(session_id, current_user)
    ensure_project_assignment(db, current_user, project_id, "developer")
    data = save_recording_as_case(
        session_id,
        title=title,
        project_id=project_id,
        url=url,
        browser_type=browser_type,
        db=db,
    )
    _recording_owners.pop(session_id, None)
    return DataResponse(data=data)
