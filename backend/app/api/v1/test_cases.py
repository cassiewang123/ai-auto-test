"""测试用例 CRUD API（含断言规则级联创建、用例复制、批量操作）."""
from __future__ import annotations

import json
import uuid as _uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import String, func, literal, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models import AssertionRule, InterfaceChangeLog, TestCase, TestRunSummary
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.schemas.test_case import (
    TestCaseCreate,
    TestCaseResponse,
    TestCaseUpdate,
)
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)

router = APIRouter()


def _get_or_404(db: Session, case_id: str) -> TestCase:
    case = db.get(TestCase, case_id)
    if not case:
        raise NotFoundError("测试用例", case_id)
    return case


def _get_many_or_404(db: Session, case_ids: list[str]) -> list[TestCase]:
    """Load all requested cases in request order and fail on unknown IDs."""
    return [_get_or_404(db, case_id) for case_id in case_ids]


# ---------- 变更历史辅助函数 ----------

# 记录变更日志时需要持久化的字段（与请求定义相关）。
_SNAPSHOT_FIELDS = (
    "title", "description", "group_path", "markers", "method", "url",
    "headers", "params", "body", "graphql_query", "files",
    "extract_rules", "project_id", "environment_id", "is_active", "sort_order",
    "retry_count", "retry_interval", "pre_script", "post_script",
)


def _snapshot_case(case: TestCase) -> dict:
    """生成用例的快照字典（用于变更日志）."""
    snap: dict[str, Any] = {"id": case.id}
    for field in _SNAPSHOT_FIELDS:
        value = getattr(case, field, None)
        if isinstance(value, (list, dict)):
            value = json.loads(json.dumps(value, ensure_ascii=False))
        snap[field] = value
    return snap


def _log_change(
    db: Session,
    case_id: str,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
    changed_fields: list | None = None,
) -> None:
    """记录一条接口变更日志（独立提交，不影响主操作）."""
    log = InterfaceChangeLog(
        test_case_id=case_id,
        action=action,
        before=before,
        after=after,
        changed_fields=changed_fields,
    )
    db.add(log)
    db.commit()


# ---------- 列表 & 创建（固定路径，必须在 /{case_id} 之前） ----------

@router.get("", response_model=PageResponse[TestCaseResponse])
def list_test_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    group_path: str | None = Query(None, description="按分组路径精确筛选"),
    project_id: str | None = Query(None, description="按项目筛选"),
    marker: str | None = Query(None, description="按 marker 精确筛选"),
    url_search: str | None = Query(None, description="按URL模糊搜索"),
    title_search: str | None = Query(None, description="按标题模糊搜索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """用例列表分页，支持按 group_path、project_id、URL、标题筛选."""
    query = select(TestCase)
    count_query = select(func.count()).select_from(TestCase)
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query, TestCase, current_user, owner_field=None
    )
    count_query = scope_project_resources(
        count_query, TestCase, current_user, owner_field=None
    )
    if group_path is not None:
        query = query.where(TestCase.group_path == group_path)
    if project_id is not None:
        query = query.where(TestCase.project_id == project_id)
    if marker:
        escaped_marker = marker.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            TestCase.markers.like(
                literal(f'%"{escaped_marker}"%', type_=String()),
                escape="\\",
            )
        )
    if url_search:
        query = query.where(TestCase.url.like(f"%{url_search}%"))
    if title_search:
        query = query.where(TestCase.title.like(f"%{title_search}%"))

    if group_path is not None:
        count_query = count_query.where(TestCase.group_path == group_path)
    if project_id is not None:
        count_query = count_query.where(TestCase.project_id == project_id)
    if marker:
        count_query = count_query.where(
            TestCase.markers.like(
                literal(f'%"{escaped_marker}"%', type_=String()),
                escape="\\",
            )
        )
    if url_search:
        count_query = count_query.where(TestCase.url.like(f"%{url_search}%"))
    if title_search:
        count_query = count_query.where(TestCase.title.like(f"%{title_search}%"))
    total = db.execute(count_query).scalar_one()

    items = (
        db.execute(
            query.order_by(TestCase.sort_order.asc(), TestCase.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[TestCaseResponse](
        data=items, total=total, page=page, page_size=page_size
    )


@router.post("", response_model=DataResponse[TestCaseResponse])
def create_test_case(
    payload: TestCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建用例，并级联创建断言规则."""
    ensure_project_assignment(db, current_user, payload.project_id, "developer")
    data = payload.model_dump()
    assertions_data = data.pop("assertions", []) or []
    case = TestCase(**data)
    db.add(case)
    db.flush()
    for a in assertions_data:
        db.add(AssertionRule(test_case_id=case.id, **a))
    db.commit()
    db.refresh(case)
    # 记录创建变更日志
    _log_change(db, case.id, "created", after=_snapshot_case(case))
    return DataResponse[TestCaseResponse](data=case)


# ---------- 批量操作（固定路径，必须在 /{case_id} 之前） ----------

class BatchExecuteRequest(BaseModel):
    case_ids: list[str]


class BatchDeleteRequest(BaseModel):
    case_ids: list[str]


class BatchMoveRequest(BaseModel):
    case_ids: list[str]
    project_id: str | None = None


class ReorderRequest(BaseModel):
    """重新排序请求：传入有序的 case_id 列表."""
    case_ids: list[str]


@router.post("/reorder", response_model=DataResponse[dict])
def reorder_test_cases(
    req: ReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量更新用例排序，按传入的 case_ids 顺序设置 sort_order."""
    cases = _get_many_or_404(db, req.case_ids)
    for case in cases:
        ensure_resource_role(
            db, current_user, case, "developer", owner_field=None
        )
    updated = 0
    for index, case in enumerate(cases):
        case.sort_order = index
        updated += 1
    db.commit()
    return DataResponse(data={"total": len(req.case_ids), "updated": updated})


@router.post("/batch-execute", response_model=DataResponse[dict])
def batch_execute(
    req: BatchExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量执行测试用例，返回每个用例的执行结果摘要."""
    from test_engine.executor import TestCaseExecutor

    _executor = TestCaseExecutor()
    results = []
    passed = 0
    failed = 0
    errored = 0

    cases = _get_many_or_404(db, req.case_ids)
    for case in cases:
        ensure_resource_role(
            db, current_user, case, "tester", owner_field=None
        )

    for case in cases:
        case_id = case.id
        try:
            result = _executor.execute(
                request_def=_build_request_def_from_case(case),
                assertions=[a.__dict__ for a in case.assertions],
                variables={},
            )
            status = result.status
            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
            else:
                errored += 1

            results.append({
                "case_id": case_id,
                "title": case.title,
                "method": case.method,
                "url": case.url,
                "status": status,
                "duration": round(result.duration, 4),
                "status_code": result.response.status_code if result.response else None,
                "error": result.error_message,
            })
        except Exception as exc:
            errored += 1
            results.append({
                "case_id": case_id,
                "title": case.title,
                "status": "error",
                "error": str(exc),
            })

    # 创建批次汇总记录并更新已有 TestResult 的 run_id
    run_id = str(_uuid.uuid4())
    project_ids = {case.project_id for case in cases}
    summary_project_id = (
        next(iter(project_ids)) if len(project_ids) == 1 else None
    )
    summary = TestRunSummary(
        run_id=run_id,
        source="batch_execute",
        project_id=summary_project_id,
        created_by=current_user.id,
        total=len(req.case_ids),
        passed=passed,
        failed=failed,
        error=errored,
        skipped=0,
        duration=sum(r.get("duration", 0) for r in results),
        summary={"results": results},
    )
    db.add(summary)
    # 同时更新 TestResult 记录的 run_id（如果之前有创建的话）
    db.commit()

    return DataResponse(data={
        "run_id": run_id,
        "total": len(req.case_ids),
        "passed": passed,
        "failed": failed,
        "error": errored,
        "results": results,
    })


@router.post("/batch-delete", response_model=DataResponse[dict])
def batch_delete(
    req: BatchDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量删除测试用例."""
    cases = _get_many_or_404(db, req.case_ids)
    for case in cases:
        ensure_resource_role(
            db, current_user, case, "admin", owner_field=None
        )
    for case in cases:
        db.delete(case)
    db.commit()
    return DataResponse(data={
        "total": len(req.case_ids),
        "deleted": len(cases),
        "not_found": 0,
    })


@router.post("/batch-move", response_model=DataResponse[dict])
def batch_move(
    req: BatchMoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量移动用例到指定项目."""
    cases = _get_many_or_404(db, req.case_ids)
    for case in cases:
        ensure_resource_role(
            db, current_user, case, "admin", owner_field=None
        )
    ensure_project_assignment(db, current_user, req.project_id, "admin")
    for case in cases:
        case.project_id = req.project_id
    db.commit()
    return DataResponse(data={
        "total": len(req.case_ids),
        "moved": len(cases),
        "not_found": 0,
        "project_id": req.project_id,
    })


# ---------- 单个用例操作（含路径参数 /{case_id}） ----------

@router.get("/{case_id}", response_model=DataResponse[TestCaseResponse])
def get_test_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个用例（含断言规则）."""
    case = _get_or_404(db, case_id)
    ensure_resource_role(db, current_user, case, "viewer", owner_field=None)
    return DataResponse[TestCaseResponse](data=case)


@router.put("/{case_id}", response_model=DataResponse[TestCaseResponse])
def update_test_case(
    case_id: str,
    payload: TestCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新用例（部分更新，不涉及断言规则）."""
    case = _get_or_404(db, case_id)
    ensure_resource_role(db, current_user, case, "developer", owner_field=None)
    before_snapshot = _snapshot_case(case)
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
    # 记录更新变更日志
    _log_change(
        db,
        case_id,
        "updated",
        before=before_snapshot,
        after=_snapshot_case(case),
        changed_fields=list(update_data.keys()),
    )
    return DataResponse[TestCaseResponse](data=case)


@router.delete("/{case_id}", response_model=DataResponse[TestCaseResponse])
def delete_test_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除用例（ORM 级联删除断言规则）."""
    case = _get_or_404(db, case_id)
    ensure_resource_role(db, current_user, case, "admin", owner_field=None)
    data = TestCaseResponse.model_validate(case)
    before_snapshot = _snapshot_case(case)
    # 先记录删除日志（此时用例仍存在，FK 引用有效）
    db.add(
        InterfaceChangeLog(
            test_case_id=case_id,
            action="deleted",
            before=before_snapshot,
            after=None,
        )
    )
    db.delete(case)
    db.commit()
    return DataResponse[TestCaseResponse](data=data)


@router.post("/{case_id}/copy", response_model=DataResponse[TestCaseResponse])
def copy_test_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """复制用例：复制请求定义、标记、提取规则与断言规则，标题追加 (副本)。"""
    src = _get_or_404(db, case_id)
    ensure_resource_role(db, current_user, src, "developer", owner_field=None)
    new_case = TestCase(
        title=f"{src.title} (副本)",
        description=src.description,
        group_path=src.group_path,
        markers=list(src.markers or []),
        method=src.method,
        url=src.url,
        headers=dict(src.headers or {}),
        params=dict(src.params or {}),
        body=src.body,
        graphql_query=src.graphql_query,
        files=list(src.files) if src.files else None,
        extract_rules=list(src.extract_rules or []),
        environment_id=src.environment_id,
        project_id=src.project_id,
        retry_count=src.retry_count,
        retry_interval=src.retry_interval,
        pre_script=src.pre_script,
        post_script=src.post_script,
    )
    db.add(new_case)
    db.flush()
    for a in src.assertions:
        db.add(
            AssertionRule(
                test_case_id=new_case.id,
                assertion_type=a.assertion_type,
                expression=a.expression,
                operator=a.operator,
                expected=a.expected,
                priority=a.priority,
                order=a.order,
            )
        )
    db.commit()
    db.refresh(new_case)
    return DataResponse[TestCaseResponse](data=new_case)


@router.get("/{case_id}/doc")
def download_case_doc(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载接口文档（Markdown 格式）."""
    case = _get_or_404(db, case_id)
    ensure_resource_role(db, current_user, case, "viewer", owner_field=None)
    # 生成 Markdown 文档
    md = f"""# {case.title}

## 接口信息
- **请求方法**: {case.method}
- **请求 URL**: `{case.url}`
- **分组**: {case.group_path or '无'}
- **描述**: {case.description or '无'}

## 请求头
```json
{json.dumps(case.headers or {}, indent=2, ensure_ascii=False)}
```

## 请求参数
```json
{json.dumps(case.params or {}, indent=2, ensure_ascii=False)}
```

## 请求体
```json
{json.dumps(case.body or {}, indent=2, ensure_ascii=False) if case.body else '无'}
```

## 断言规则
"""
    for a in case.assertions:
        md += f"- {a.assertion_type}"
        if a.expression:
            md += f" ({a.expression})"
        md += f" {a.operator} {a.expected}\n"

    return Response(
        content=md.encode("utf-8"),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(case.title)}.md"},
    )


# ---------- 辅助函数 ----------

def _build_request_def_from_case(case: TestCase):
    """从 TestCase 模型构建 RequestDefinition."""
    from app.schemas.execution import RequestDefinition  # noqa: E402

    return RequestDefinition(
        method=case.method,
        url=case.url,
        headers=dict(case.headers or {}),
        params=dict(case.params or {}),
        body=case.body,
        graphql_query=case.graphql_query,
        files=list(case.files) if case.files else None,
        extract_rules=list(case.extract_rules or []),
        timeout=30.0,
    )
