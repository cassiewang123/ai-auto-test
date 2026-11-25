"""接口用例库（用例管理）API.

端点：
    GET    /api-cases              — 列表（按项目/模块/方法/场景/优先级/关键词筛选）
    GET    /api-cases/stats        — 统计
    GET    /api-cases/groups       — 模块（分组）列表及用例数量
    POST   /api-cases              — 手工创建
    POST   /api-cases/bulk-import  — 批量导入生成结果
    POST   /api-cases/batch-move   — 批量移动到指定模块
    POST   /api-cases/batch-delete — 批量删除
    GET    /api-cases/export       — 导出 Excel
    GET    /api-cases/{id}         — 详情
    PUT    /api-cases/{id}         — 更新
    DELETE /api-cases/{id}         — 删除

注意：路由顺序上 ``/stats``、``/groups``、``/export``、``/bulk-import`` 必须
声明在 ``/{case_id}`` 之前，避免被通配路由匹配。

模块（分组）通过 ``group_path`` 表达层级，例如 ``swgd-imap-content/ApiType 码表``；
传入父级模块时应命中其下所有子模块，因此这里用「路径前缀」匹配而不是等值匹配。
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
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.api_case_record import ApiCaseRecord
from app.models.user import User
from app.schemas.api_case_record import (
    ApiCaseBatchIdsRequest,
    ApiCaseBulkImportRequest,
    ApiCaseBulkImportResponse,
    ApiCaseGroupItem,
    ApiCaseRecordCreate,
    ApiCaseRecordResponse,
    ApiCaseRecordStats,
    ApiCaseRecordUpdate,
)
from app.schemas.common import DataResponse, PageResponse, ResponseBase
from app.services.auth_service import get_current_user

router = APIRouter()

_VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_VALID_CASE_TYPES = {"normal", "exception", "boundary", "permission"}
_VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
_VALID_STATUSES = {"draft", "active", "archived"}

CASE_TYPE_LABEL = {
    "normal": "正常",
    "exception": "异常",
    "boundary": "边界",
    "permission": "权限",
}


def _get_or_404(db: Session, case_id: str) -> ApiCaseRecord:
    item = db.get(ApiCaseRecord, case_id)
    if not item:
        raise NotFoundError("接口用例", case_id)
    return item


def _normalize_path(value: str | None) -> str:
    """规范化分组路径：去空白、去首尾/重复斜杠."""
    parts = [part.strip() for part in (value or "").split("/")]
    return "/".join(part for part in parts if part)


def _group_filter_clause(group_path: str):
    """构造「含本分组与全部子分组」的筛选条件.

    空字符串表示「未分组」（group_path 为 NULL 或空串），这样前端选
    「未分组」时也能正确筛选。
    """
    path = _normalize_path(group_path)
    if not path:
        return or_(
            ApiCaseRecord.group_path.is_(None), ApiCaseRecord.group_path == ""
        )
    return or_(
        ApiCaseRecord.group_path == path,
        ApiCaseRecord.group_path.startswith(f"{path}/", autoescape=True),
    )


def _validate(
    method: str | None = None,
    case_type: str | None = None,
    priority: str | None = None,
    status: str | None = None,
) -> None:
    if method and method.upper() not in _VALID_METHODS:
        raise ValidationError(f"不支持的请求方法: {method}")
    if case_type and case_type not in _VALID_CASE_TYPES:
        raise ValidationError(f"不支持的场景类型: {case_type}")
    if priority and priority not in _VALID_PRIORITIES:
        raise ValidationError(f"不支持的优先级: {priority}")
    if status and status not in _VALID_STATUSES:
        raise ValidationError(f"不支持的状态: {status}")


def _apply_filters(query, params: dict):
    if params.get("project_id"):
        query = query.where(ApiCaseRecord.project_id == params["project_id"])
    # group_path 为空字符串是有效筛选（未分组），因此判断 is not None
    if params.get("group_path") is not None:
        query = query.where(_group_filter_clause(params["group_path"]))
    if params.get("method"):
        query = query.where(ApiCaseRecord.method == params["method"].upper())
    if params.get("case_type"):
        query = query.where(ApiCaseRecord.case_type == params["case_type"])
    if params.get("priority"):
        query = query.where(ApiCaseRecord.priority == params["priority"])
    if params.get("status"):
        query = query.where(ApiCaseRecord.status == params["status"])
    if params.get("keyword"):
        pattern = f"%{params['keyword']}%"
        query = query.where(ApiCaseRecord.title.like(pattern))
    return query


@router.get("", response_model=PageResponse[ApiCaseRecordResponse])
def list_api_cases(
    project_id: str | None = Query(None),
    group_path: str | None = Query(
        None, description="按模块筛选；父级模块包含其下所有子模块，空串表示未分组"
    ),
    method: str | None = Query(None),
    case_type: str | None = Query(None),
    priority: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """接口用例列表."""
    filters = {
        "project_id": project_id,
        "group_path": group_path,
        "method": method,
        "case_type": case_type,
        "priority": priority,
        "status": status,
        "keyword": keyword,
    }
    base = select(ApiCaseRecord).where(ApiCaseRecord.is_active.is_(True))
    count_q = select(func.count()).select_from(ApiCaseRecord).where(
        ApiCaseRecord.is_active.is_(True)
    )
    base = _apply_filters(base, filters)
    count_q = _apply_filters(count_q, filters)

    total = db.execute(count_q).scalar_one()
    items = (
        db.execute(
            base.order_by(ApiCaseRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[ApiCaseRecordResponse](
        data=[ApiCaseRecordResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DataResponse[ApiCaseRecordStats])
def api_case_stats(
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """接口用例统计."""
    query = select(ApiCaseRecord).where(ApiCaseRecord.is_active.is_(True))
    if project_id:
        query = query.where(ApiCaseRecord.project_id == project_id)
    items = db.execute(query).scalars().all()
    normalized_paths = {_normalize_path(item.group_path) for item in items}
    normalized_paths.discard("")
    return DataResponse[ApiCaseRecordStats](
        data=ApiCaseRecordStats(
            total=len(items),
            normal=sum(1 for item in items if item.case_type == "normal"),
            exception=sum(1 for item in items if item.case_type == "exception"),
            boundary=sum(1 for item in items if item.case_type == "boundary"),
            permission=sum(1 for item in items if item.case_type == "permission"),
            p0=sum(1 for item in items if item.priority == "P0"),
            group_count=len(normalized_paths),
        )
    )


@router.get("/groups", response_model=DataResponse[list[ApiCaseGroupItem]])
def api_case_groups(
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """模块（分组）列表：返回题库中出现过的全部 group_path 及其父级路径.

    每个模块带上直接用例数与「含子模块」的累计用例数，供用例管理页按模块
    分组展示与筛选使用。用例引用了某个路径但父级尚未出现时，也会补齐父级，
    保证前端能构建完整的模块树。
    """
    query = select(ApiCaseRecord.group_path).where(
        ApiCaseRecord.is_active.is_(True), ApiCaseRecord.group_path.is_not(None)
    )
    if project_id:
        query = query.where(ApiCaseRecord.project_id == project_id)
    raw_paths = [path for path in db.execute(query).scalars().all() if path]

    direct_counts: dict[str, int] = {}
    for raw in raw_paths:
        path = _normalize_path(raw)
        if not path:
            continue
        direct_counts[path] = direct_counts.get(path, 0) + 1

    all_paths: set[str] = set()
    for path in direct_counts:
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            all_paths.add("/".join(parts[:index]))

    groups: list[ApiCaseGroupItem] = []
    for path in sorted(all_paths):
        total = sum(
            count
            for case_path, count in direct_counts.items()
            if case_path == path or case_path.startswith(f"{path}/")
        )
        groups.append(
            ApiCaseGroupItem(
                path=path,
                name=path.rsplit("/", 1)[-1],
                parent_path=path.rsplit("/", 1)[0] if "/" in path else None,
                direct_count=direct_counts.get(path, 0),
                total_count=total,
            )
        )
    return DataResponse[list[ApiCaseGroupItem]](data=groups)


@router.post("/batch-move", response_model=DataResponse[dict])
def batch_move_api_cases(
    payload: ApiCaseBatchIdsRequest,
    db: Session = Depends(get_db),
):
    """把选中的用例批量移动到指定模块（分组）.

    ``group_path`` 传空或 null 表示移出模块（未分组）。
    """
    if not payload.case_ids:
        raise ValidationError("请选择要移动的用例")
    target = _normalize_path(payload.group_path) or None

    items = (
        db.execute(
            select(ApiCaseRecord).where(ApiCaseRecord.id.in_(payload.case_ids))
        )
        .scalars()
        .all()
    )
    if not items:
        raise NotFoundError("接口用例", ",".join(payload.case_ids[:3]))
    for item in items:
        item.group_path = target
    db.commit()
    return DataResponse[dict](data={"moved": len(items), "group_path": target})


@router.post("/batch-delete", response_model=DataResponse[dict])
def batch_delete_api_cases(
    payload: ApiCaseBatchIdsRequest,
    db: Session = Depends(get_db),
):
    """批量删除选中的用例."""
    if not payload.case_ids:
        raise ValidationError("请选择要删除的用例")
    items = (
        db.execute(
            select(ApiCaseRecord).where(ApiCaseRecord.id.in_(payload.case_ids))
        )
        .scalars()
        .all()
    )
    for item in items:
        db.delete(item)
    db.commit()
    return DataResponse[dict](data={"deleted": len(items)})


@router.get("/export")
def export_api_cases(
    project_id: str | None = Query(None),
    group_path: str | None = Query(None),
    method: str | None = Query(None),
    case_type: str | None = Query(None),
    priority: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """按当前筛选条件导出接口用例为 Excel（.xlsx）."""
    filters = {
        "project_id": project_id,
        "group_path": group_path,
        "method": method,
        "case_type": case_type,
        "priority": priority,
        "status": status,
        "keyword": keyword,
    }
    query = select(ApiCaseRecord).where(ApiCaseRecord.is_active.is_(True))
    query = _apply_filters(query, filters)
    items = (
        db.execute(query.order_by(ApiCaseRecord.created_at.desc()))
        .scalars()
        .all()
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "接口用例"
    headers = [
        "序号",
        "用例标题",
        "场景",
        "方法",
        "URL",
        "优先级",
        "状态",
        "请求头",
        "查询参数",
        "请求体",
        "断言",
        "关联接口",
        "分组",
        "说明",
        "创建时间",
    ]
    sheet.append(headers)

    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="F0F0F0")
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")

    import json

    status_label = {"draft": "草稿", "active": "已确认", "archived": "已归档"}
    for index, item in enumerate(items, start=1):
        sheet.append(
            [
                index,
                item.title,
                CASE_TYPE_LABEL.get(item.case_type, item.case_type),
                item.method,
                item.url,
                item.priority,
                status_label.get(item.status, item.status),
                json.dumps(item.headers or {}, ensure_ascii=False),
                json.dumps(item.params or {}, ensure_ascii=False),
                json.dumps(item.body, ensure_ascii=False) if item.body is not None else "",
                json.dumps(item.assertions or [], ensure_ascii=False),
                item.interface_name or "",
                item.group_path or "",
                item.description or "",
                item.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if item.created_at
                else "",
            ]
        )

    widths = [6, 38, 8, 8, 42, 8, 10, 28, 28, 40, 40, 22, 22, 30, 20]
    for col_index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(col_index)].width = width
    wrap = Alignment(wrap_text=True, vertical="top")
    center = Alignment(horizontal="center", vertical="top")
    for row in sheet.iter_rows(min_row=2):
        for col_index, cell in enumerate(row, start=1):
            cell.border = border
            cell.alignment = center if col_index in {1, 3, 4, 6, 7} else wrap
    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    filename = f"接口用例-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"api-cases.xlsx\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.post("/bulk-import", response_model=DataResponse[ApiCaseBulkImportResponse])
def bulk_import_api_cases(
    payload: ApiCaseBulkImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把接口用例生成结果批量写入接口用例库."""
    if not payload.cases:
        raise ValidationError("没有可导入的用例")

    created_ids: list[str] = []
    for case in payload.cases:
        title = str(case.get("title") or "").strip()
        url = str(case.get("url") or "").strip()
        if not title or not url:
            continue
        method = str(case.get("method") or "GET").upper()
        case_type = str(case.get("case_type") or "normal")
        priority = str(case.get("priority") or "P1")
        # 按模块批量生成时，同一次导入的用例来自多个接口，各带自己的
        # 接口名与分组路径；单接口导入时回落到请求级字段。
        interface_name = str(
            case.get("interface_name") or payload.interface_name or ""
        ).strip()
        group_path = str(
            case.get("group_path") or payload.group_path or ""
        ).strip()
        item = ApiCaseRecord(
            title=title,
            method=method,
            url=url,
            headers=case.get("headers") or {},
            params=case.get("params") or {},
            body=case.get("body"),
            assertions=case.get("assertions") or [],
            case_type=case_type if case_type in _VALID_CASE_TYPES else "normal",
            priority=priority if priority in _VALID_PRIORITIES else "P1",
            status="active",
            source="ai",
            description=case.get("description"),
            # 防御：接口名/分组可能来自超长标题，截断到字段上限避免 422
            interface_name=interface_name[:256] or None,
            group_path=group_path[:256] or None,
            project_id=case.get("project_id") or payload.project_id,
            created_by=current_user.id,
        )
        db.add(item)
        db.flush()
        created_ids.append(item.id)

    if not created_ids:
        raise ValidationError("用例缺少标题或 URL，未能导入")
    db.commit()
    return DataResponse[ApiCaseBulkImportResponse](
        data=ApiCaseBulkImportResponse(
            created_count=len(created_ids), case_ids=created_ids
        )
    )


@router.post("", response_model=DataResponse[ApiCaseRecordResponse])
def create_api_case(
    payload: ApiCaseRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手工创建接口用例."""
    _validate(payload.method, payload.case_type, payload.priority, payload.status)
    data = payload.model_dump()
    data["group_path"] = _normalize_path(data.get("group_path")) or None
    item = ApiCaseRecord(
        **data,
        source="manual",
        created_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return DataResponse[ApiCaseRecordResponse](
        data=ApiCaseRecordResponse.model_validate(item)
    )


@router.get("/{case_id}", response_model=DataResponse[ApiCaseRecordResponse])
def get_api_case(case_id: str, db: Session = Depends(get_db)):
    """接口用例详情."""
    item = _get_or_404(db, case_id)
    return DataResponse[ApiCaseRecordResponse](
        data=ApiCaseRecordResponse.model_validate(item)
    )


@router.put("/{case_id}", response_model=DataResponse[ApiCaseRecordResponse])
def update_api_case(
    case_id: str,
    payload: ApiCaseRecordUpdate,
    db: Session = Depends(get_db),
):
    """更新接口用例（编辑标题/方法/URL/模块/参数/请求体/断言等）."""
    item = _get_or_404(db, case_id)
    changes = payload.model_dump(exclude_unset=True)
    _validate(
        changes.get("method"),
        changes.get("case_type"),
        changes.get("priority"),
        changes.get("status"),
    )
    if "group_path" in changes:
        # 允许显式置空（把用例移出模块）
        changes["group_path"] = _normalize_path(changes["group_path"]) or None
    if "interface_name" in changes and changes["interface_name"] is not None:
        changes["interface_name"] = str(changes["interface_name"])[:256] or None
    for field, value in changes.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return DataResponse[ApiCaseRecordResponse](
        data=ApiCaseRecordResponse.model_validate(item)
    )


@router.delete("/{case_id}", response_model=ResponseBase)
def delete_api_case(case_id: str, db: Session = Depends(get_db)):
    """删除接口用例."""
    item = _get_or_404(db, case_id)
    db.delete(item)
    db.commit()
    return ResponseBase()
