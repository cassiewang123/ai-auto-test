"""功能测试用例库 API.

与 API 自动化用例（``/test-cases``）分离：功能测试用例描述人工执行的前置
条件、操作步骤与预期结果，不绑定 HTTP 请求。

端点：
    GET    /functional-test-cases              — 列表（按模块/优先级/状态/需求筛选）
    GET    /functional-test-cases/stats        — 统计
    POST   /functional-test-cases              — 手工创建
    GET    /functional-test-cases/{id}         — 详情
    PUT    /functional-test-cases/{id}         — 更新
    DELETE /functional-test-cases/{id}         — 删除
    POST   /functional-test-cases/{id}/executions  — 登记人工执行结果
    GET    /functional-test-cases/{id}/executions  — 执行历史
"""
from __future__ import annotations

import io
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.functional_test_case import (
    FunctionalCaseExecution,
    FunctionalTestCase,
)
from app.models.requirement import Requirement
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse, ResponseBase
from app.schemas.functional_test_case import (
    ExecutionCreate,
    ExecutionResponse,
    FunctionalTestCaseCreate,
    FunctionalTestCaseResponse,
    FunctionalTestCaseStats,
    FunctionalTestCaseUpdate,
)
from app.services.auth_service import get_current_user

router = APIRouter()

_VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
_VALID_STATUSES = {"draft", "active", "deprecated"}
_VALID_RESULTS = {"passed", "failed", "blocked", "skipped"}
_VALID_CATEGORIES = {"功能", "异常", "边界", "权限", "安全"}


def _get_or_404(db: Session, case_id: str) -> FunctionalTestCase:
    item = db.get(FunctionalTestCase, case_id)
    if not item:
        raise NotFoundError("功能测试用例", case_id)
    return item


def _latest_execution(
    db: Session, case_id: str
) -> FunctionalCaseExecution | None:
    # 同一秒内多次写入时 executed_at 相同，用 order_no 兜底保证顺序稳定
    return (
        db.execute(
            select(FunctionalCaseExecution)
            .where(FunctionalCaseExecution.case_id == case_id)
            .order_by(
                FunctionalCaseExecution.order_no.desc(),
                FunctionalCaseExecution.executed_at.desc(),
            )
            .limit(1)
        )
        .scalars()
        .first()
    )


def _to_response(
    db: Session, item: FunctionalTestCase
) -> FunctionalTestCaseResponse:
    data = FunctionalTestCaseResponse.model_validate(item)
    latest = _latest_execution(db, item.id)
    if latest:
        data.last_result = latest.result
        data.last_executed_at = latest.executed_at
    return data


@router.get("", response_model=PageResponse[FunctionalTestCaseResponse])
def list_functional_cases(
    project_id: str | None = Query(None),
    requirement_id: str | None = Query(None),
    module: str | None = Query(None),
    category: str | None = Query(None),
    priority: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """功能测试用例列表."""
    query = select(FunctionalTestCase)
    count_q = select(func.count()).select_from(FunctionalTestCase)

    for field, value in (
        (FunctionalTestCase.project_id, project_id),
        (FunctionalTestCase.requirement_id, requirement_id),
        (FunctionalTestCase.module, module),
        (FunctionalTestCase.category, category),
        (FunctionalTestCase.priority, priority),
        (FunctionalTestCase.status, status),
    ):
        if value:
            query = query.where(field == value)
            count_q = count_q.where(field == value)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(FunctionalTestCase.title.like(pattern))
        count_q = count_q.where(FunctionalTestCase.title.like(pattern))

    total = db.execute(count_q).scalar_one()
    items = (
        db.execute(
            query.order_by(FunctionalTestCase.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[FunctionalTestCaseResponse](
        data=[_to_response(db, item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DataResponse[FunctionalTestCaseStats])
def functional_case_stats(
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """功能测试用例统计."""
    query = select(FunctionalTestCase)
    if project_id:
        query = query.where(FunctionalTestCase.project_id == project_id)
    items = db.execute(query).scalars().all()

    requirement_ids = {item.requirement_id for item in items if item.requirement_id}
    return DataResponse[FunctionalTestCaseStats](
        data=FunctionalTestCaseStats(
            total=len(items),
            draft=sum(1 for item in items if item.status == "draft"),
            active=sum(1 for item in items if item.status == "active"),
            deprecated=sum(1 for item in items if item.status == "deprecated"),
            p0=sum(1 for item in items if item.priority == "P0"),
            covered_requirements=len(requirement_ids),
        )
    )


@router.post("", response_model=DataResponse[FunctionalTestCaseResponse])
def create_functional_case(
    payload: FunctionalTestCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手工创建功能测试用例."""
    _validate_payload(payload.priority, payload.status, payload.category)
    if payload.requirement_id and not db.get(Requirement, payload.requirement_id):
        raise NotFoundError("需求", payload.requirement_id)

    item = FunctionalTestCase(
        **payload.model_dump(),
        source="manual",
        created_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _sync_requirement_cases(db, item.requirement_id)
    return DataResponse[FunctionalTestCaseResponse](data=_to_response(db, item))


# ---------------------------------------------------------------------------
# Excel 导出
# ---------------------------------------------------------------------------
@router.get("/export")
def export_functional_cases(
    project_id: str | None = Query(None),
    requirement_id: str | None = Query(None),
    module: str | None = Query(None),
    category: str | None = Query(None),
    priority: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """按当前筛选条件导出功能测试用例为 Excel（.xlsx）.

    导出列与页面一致：用例标题、模块、分类、优先级、前置条件、操作步骤、
    预期结果、需求追溯、状态、最近执行结果。
    """
    query = select(FunctionalTestCase).where(
        FunctionalTestCase.is_active.is_(True)
    )
    for field, value in (
        (FunctionalTestCase.project_id, project_id),
        (FunctionalTestCase.requirement_id, requirement_id),
        (FunctionalTestCase.module, module),
        (FunctionalTestCase.category, category),
        (FunctionalTestCase.priority, priority),
        (FunctionalTestCase.status, status),
    ):
        if value:
            query = query.where(field == value)
    if keyword:
        query = query.where(FunctionalTestCase.title.like(f"%{keyword}%"))

    items = (
        db.execute(query.order_by(FunctionalTestCase.created_at.desc()))
        .scalars()
        .all()
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "功能测试用例"

    headers = [
        "序号",
        "用例标题",
        "模块",
        "分类",
        "优先级",
        "前置条件",
        "操作步骤",
        "预期结果",
        "需求追溯",
        "状态",
        "最近执行结果",
    ]
    sheet.append(headers)

    # 表头样式：加粗 + 浅灰底 + 细边框
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="F0F0F0")
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")

    status_label = {"draft": "草稿", "active": "可执行", "deprecated": "已废弃"}
    result_label = {
        "passed": "通过",
        "failed": "失败",
        "blocked": "阻塞",
        "skipped": "跳过",
    }

    for index, item in enumerate(items, start=1):
        latest = _latest_execution(db, item.id)
        steps = list(item.steps or [])
        # 步骤逐行编号，Excel 中一行内换行展示，便于直接阅读
        steps_text = "\n".join(
            f"{step_index}. {step}"
            for step_index, step in enumerate(steps, start=1)
        )
        sheet.append(
            [
                index,
                item.title,
                item.module or "",
                item.category,
                item.priority,
                item.preconditions or "",
                steps_text,
                item.expected or "",
                item.trace_source or "",
                status_label.get(item.status, item.status),
                result_label.get(latest.result, latest.result) if latest else "",
            ]
        )

    # 列宽与自动换行
    widths = [6, 40, 18, 10, 10, 30, 50, 35, 28, 12, 14]
    for col_index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(col_index)].width = width
    wrap_alignment = Alignment(wrap_text=True, vertical="top")
    center_alignment = Alignment(horizontal="center", vertical="top")
    for row in sheet.iter_rows(min_row=2):
        for col_index, cell in enumerate(row, start=1):
            cell.border = border
            # 标题、步骤、前置条件、预期结果列自动换行
            cell.alignment = (
                center_alignment if col_index in {1, 4, 5, 10, 11} else wrap_alignment
            )
    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    # 文件名含中文，使用 RFC 5987 编码避免部分浏览器乱码
    filename = f"功能测试用例-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    quoted = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"functional-test-cases.xlsx\"; "
                f"filename*=UTF-8''{quoted}"
            )
        },
    )


@router.get(
    "/{case_id}", response_model=DataResponse[FunctionalTestCaseResponse]
)
def get_functional_case(case_id: str, db: Session = Depends(get_db)):
    """功能测试用例详情."""
    item = _get_or_404(db, case_id)
    return DataResponse[FunctionalTestCaseResponse](data=_to_response(db, item))


@router.put(
    "/{case_id}", response_model=DataResponse[FunctionalTestCaseResponse]
)
def update_functional_case(
    case_id: str,
    payload: FunctionalTestCaseUpdate,
    db: Session = Depends(get_db),
):
    """更新功能测试用例."""
    item = _get_or_404(db, case_id)
    changes = payload.model_dump(exclude_unset=True)
    _validate_payload(
        changes.get("priority"), changes.get("status"), changes.get("category")
    )
    previous_requirement_id = item.requirement_id
    for field, value in changes.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    # 需求变更时同步两侧的关联用例
    _sync_requirement_cases(db, previous_requirement_id)
    _sync_requirement_cases(db, item.requirement_id)
    return DataResponse[FunctionalTestCaseResponse](data=_to_response(db, item))


@router.delete("/{case_id}", response_model=ResponseBase)
def delete_functional_case(case_id: str, db: Session = Depends(get_db)):
    """删除功能测试用例（同时删除其执行记录）.

    SQLite 默认不启用外键约束，因此这里显式删除执行记录，不依赖
    ``ondelete="CASCADE"``（该约束在 Oracle/PostgreSQL 下仍然生效）。
    """
    item = _get_or_404(db, case_id)
    requirement_id = item.requirement_id
    db.execute(
        delete(FunctionalCaseExecution).where(
            FunctionalCaseExecution.case_id == case_id
        )
    )
    db.delete(item)
    db.commit()
    _sync_requirement_cases(db, requirement_id)
    return ResponseBase()


@router.post(
    "/{case_id}/executions", response_model=DataResponse[ExecutionResponse]
)
def add_execution(
    case_id: str,
    payload: ExecutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """登记一次人工执行结果."""
    _get_or_404(db, case_id)
    if payload.result not in _VALID_RESULTS:
        raise ValidationError(f"不支持的执行结果: {payload.result}")

    execution = FunctionalCaseExecution(
        case_id=case_id,
        result=payload.result,
        actual=payload.actual,
        remark=payload.remark,
        defect_ref=payload.defect_ref,
        run_label=payload.run_label,
        executed_by=current_user.id,
        order_no=_next_execution_order(db, case_id),
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return DataResponse[ExecutionResponse](
        data=ExecutionResponse.model_validate(execution)
    )


@router.get(
    "/{case_id}/executions",
    response_model=DataResponse[list[ExecutionResponse]],
)
def list_executions(case_id: str, db: Session = Depends(get_db)):
    """该用例的执行历史（最新在前）."""
    _get_or_404(db, case_id)
    items = (
        db.execute(
            select(FunctionalCaseExecution)
            .where(FunctionalCaseExecution.case_id == case_id)
            .order_by(FunctionalCaseExecution.executed_at.desc())
        )
        .scalars()
        .all()
    )
    return DataResponse[list[ExecutionResponse]](
        data=[ExecutionResponse.model_validate(item) for item in items]
    )


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _next_execution_order(db: Session, case_id: str) -> int:
    """取该用例下一个执行序号，用于同一秒内多次执行时的稳定排序."""
    current = db.execute(
        select(func.max(FunctionalCaseExecution.order_no)).where(
            FunctionalCaseExecution.case_id == case_id
        )
    ).scalar_one()
    return int(current or 0) + 1


def _validate_payload(
    priority: str | None, status: str | None, category: str | None
) -> None:
    if priority and priority not in _VALID_PRIORITIES:
        raise ValidationError(f"不支持的优先级: {priority}")
    if status and status not in _VALID_STATUSES:
        raise ValidationError(f"不支持的状态: {status}")
    if category and category not in _VALID_CATEGORIES:
        raise ValidationError(f"不支持的分类: {category}")


def _sync_requirement_cases(db: Session, requirement_id: str | None) -> None:
    """把功能测试用例的关联同步回需求，供覆盖率统计使用.

    需求的 ``case_ids`` 同时容纳 API 用例与功能用例的 ID；这里整体重算
    该需求关联的功能用例 ID，避免重复或残留。
    """
    if not requirement_id:
        return
    requirement = db.get(Requirement, requirement_id)
    if not requirement:
        return

    functional_ids = set(
        db.execute(
            select(FunctionalTestCase.id).where(
                FunctionalTestCase.requirement_id == requirement_id,
                FunctionalTestCase.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    # 保留已有的非功能用例关联（例如历史 API 用例）
    existing = list(requirement.case_ids or [])
    from app.models.test_case import TestCase  # 延迟导入避免循环依赖

    api_ids = [cid for cid in existing if db.get(TestCase, cid)]

    merged = list(dict.fromkeys([*api_ids, *sorted(functional_ids)]))
    if merged != existing:
        requirement.case_ids = merged
        if merged and requirement.status == "draft":
            requirement.status = "active"
        elif not merged and requirement.status == "active":
            requirement.status = "draft"
        db.commit()
