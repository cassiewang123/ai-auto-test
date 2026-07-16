"""测试计划 CRUD API（含计划项管理：添加/移除用例、串联执行）."""

from __future__ import annotations

import re
import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine.executor import TestCaseExecutor
from test_engine.variable_extractor import VariableExtractor

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models import TestCase, TestPlan, TestPlanItem
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse, ResponseBase
from app.schemas.test_plan import (
    TestPlanCreate,
    TestPlanItemCreate,
    TestPlanItemResponse,
    TestPlanResponse,
    TestPlanUpdate,
)
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)
from app.services.security.data_redaction import redact_sensitive_data

router = APIRouter()

# 串联执行使用的执行器与变量提取器（模块级单例，便于测试 mock）
_chain_executor = TestCaseExecutor()
_chain_extractor = VariableExtractor()

# 匹配 ${var} 形式的占位符
_TEMPLATE_VAR_PATTERN = re.compile(r"\$\{\s*(\w+)\s*\}")


def _get_plan_or_404(db: Session, plan_id: str) -> TestPlan:
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise NotFoundError("测试计划", plan_id)
    return plan


def _sort_items(plan: TestPlan) -> TestPlan:
    """按 order 升序排列计划项（就地排序）。"""
    plan.items.sort(key=lambda i: i.order)
    return plan


def _to_plan_response(plan: TestPlan) -> TestPlanResponse:
    _sort_items(plan)
    return cast(
        TestPlanResponse,
        TestPlanResponse.model_validate(plan),
    )


# ---------------------------------------------------------------------------
# 串联执行辅助函数
# ---------------------------------------------------------------------------


def _render_template(obj: Any, context: dict[str, Any]) -> Any:
    """递归替换 obj 中的 ${var} 占位符，使用 context 中的值.

    支持字符串、字典、列表的递归替换。未命中变量保持原样。
    非字符串/字典/列表类型原样返回。
    """
    if isinstance(obj, str):

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in context:
                return str(context[key])
            # 未知变量保持原样
            return match.group(0)

        return str(_TEMPLATE_VAR_PATTERN.sub(repl, obj))
    if isinstance(obj, dict):
        return {k: _render_template(v, context) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_render_template(v, context) for v in obj]
    return obj


def _build_chain_request_def(case: TestCase, context: dict[str, Any]):
    """从 TestCase 模型构建已渲染变量的 RequestDefinition."""
    from app.schemas.execution import RequestDefinition

    return RequestDefinition(
        method=case.method,
        url=_render_template(case.url, context),
        headers=_render_template(dict(case.headers or {}), context),
        params=_render_template(dict(case.params or {}), context),
        body=_render_template(case.body, context) if case.body is not None else None,
        graphql_query=case.graphql_query,
        files=list(case.files) if case.files else None,
        extract_rules=list(case.extract_rules or []),
        timeout=30.0,
    )


def _build_assertions_from_case(case: TestCase) -> list[dict]:
    """从 TestCase 关联的断言规则构建断言列表."""
    assertions: list[dict] = []
    for a in sorted(case.assertions, key=lambda x: x.order):
        assertions.append(
            {
                "assertion_type": a.assertion_type,
                "expression": a.expression,
                "operator": a.operator,
                "expected": a.expected,
                "priority": a.priority,
                "order": a.order,
            }
        )
    return assertions


def _serialize_chain_result(result) -> dict:
    """将 ExecutionResult 序列化为可 JSON 响应的字典."""
    return cast(
        dict[str, Any],
        redact_sensitive_data(
            {
                "test_case_id": result.test_case_id,
                "status": result.status,
                "duration": round(result.duration, 4),
                "request": result.request.model_dump() if result.request else None,
                "response": {
                    "status_code": result.response.status_code,
                    "headers": result.response.headers,
                    "body": result.response.body,
                    "elapsed": round(result.response.elapsed, 4),
                    "text": result.response.text[:5000] if result.response.text else "",
                }
                if result.response
                else None,
                "assertion_results": [r.model_dump() for r in result.assertion_results],
                "extracted_variables": [v.model_dump() for v in result.extracted_variables],
                "error_message": result.error_message,
                "executed_at": result.executed_at.isoformat(),
            }
        ),
    )


@router.get("", response_model=PageResponse[TestPlanResponse])
def list_test_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    project_id: str | None = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """计划列表分页。"""
    query = select(TestPlan)
    count_query = select(func.count()).select_from(TestPlan)
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(query, TestPlan, current_user)
    count_query = scope_project_resources(count_query, TestPlan, current_user)
    if project_id is not None:
        query = query.where(TestPlan.project_id == project_id)
        count_query = count_query.where(TestPlan.project_id == project_id)

    total = db.execute(count_query).scalar_one()
    plans = list(
        db.execute(query.order_by(TestPlan.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return PageResponse[TestPlanResponse](
        data=[_to_plan_response(plan) for plan in plans],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{plan_id}", response_model=DataResponse[TestPlanResponse])
def get_test_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取计划详情（含按 order 排序的用例列表）."""
    plan = _get_plan_or_404(db, plan_id)
    ensure_resource_role(db, current_user, plan, "viewer")
    return DataResponse[TestPlanResponse](data=_to_plan_response(plan))


@router.post("", response_model=DataResponse[TestPlanResponse])
def create_test_plan(
    payload: TestPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建计划。"""
    ensure_project_assignment(db, current_user, payload.project_id, "developer")
    plan = TestPlan(
        **payload.model_dump(),
        created_by=current_user.id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return DataResponse[TestPlanResponse](data=_to_plan_response(plan))


@router.put("/{plan_id}", response_model=DataResponse[TestPlanResponse])
def update_test_plan(
    plan_id: str,
    payload: TestPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新计划（部分更新）。"""
    plan = _get_plan_or_404(db, plan_id)
    ensure_resource_role(db, current_user, plan, "developer")
    update_data = payload.model_dump(exclude_unset=True)
    if "project_id" in update_data and update_data["project_id"] is None:
        raise ValidationError("测试计划必须归属于项目")
    if "project_id" in update_data and update_data["project_id"] != plan.project_id:
        ensure_resource_role(db, current_user, plan, "admin")
        ensure_project_assignment(db, current_user, update_data["project_id"], "admin")
        target_project_id = update_data["project_id"]
        if any(item.test_case is not None and item.test_case.project_id != target_project_id for item in plan.items):
            raise ValidationError("迁移计划前必须移除其他项目的测试用例")
    for field, value in update_data.items():
        setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    return DataResponse[TestPlanResponse](data=_to_plan_response(plan))


@router.delete("/{plan_id}", response_model=DataResponse[TestPlanResponse])
def delete_test_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除计划（ORM 级联删除计划项）。"""
    plan = _get_plan_or_404(db, plan_id)
    ensure_resource_role(db, current_user, plan, "admin")
    data = _to_plan_response(plan)
    db.delete(plan)
    db.commit()
    return DataResponse[TestPlanResponse](data=data)


# ---------------------------------------------------------------------------
# 计划项管理
# ---------------------------------------------------------------------------
@router.post("/{plan_id}/items", response_model=DataResponse[TestPlanItemResponse])
def add_plan_item(
    plan_id: str,
    payload: TestPlanItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """添加用例到计划（带执行顺序）。"""
    plan = _get_plan_or_404(db, plan_id)
    ensure_resource_role(db, current_user, plan, "developer")
    case = db.get(TestCase, payload.test_case_id)
    if not case:
        raise NotFoundError("测试用例", payload.test_case_id)
    ensure_resource_role(db, current_user, case, "developer", owner_field=None)
    if case.project_id != plan.project_id:
        raise ValidationError("测试计划与测试用例必须属于同一项目")
    item = TestPlanItem(
        plan_id=plan_id,
        test_case_id=payload.test_case_id,
        order=payload.order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return DataResponse[TestPlanItemResponse](data=TestPlanItemResponse.model_validate(item))


@router.delete("/{plan_id}/items/{case_id}", response_model=ResponseBase)
def remove_plan_item(
    plan_id: str,
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从计划移除用例。"""
    plan = _get_plan_or_404(db, plan_id)
    ensure_resource_role(db, current_user, plan, "developer")
    item = db.execute(
        select(TestPlanItem).where(
            TestPlanItem.plan_id == plan_id,
            TestPlanItem.test_case_id == case_id,
        )
    ).scalar_one_or_none()
    if not item:
        raise NotFoundError("计划项", case_id)
    db.delete(item)
    db.commit()
    return ResponseBase()


# ---------------------------------------------------------------------------
# 串联执行（多接口串联与变量传递）
# ---------------------------------------------------------------------------


@router.post("/{plan_id}/execute-chain", response_model=DataResponse[dict])
def execute_chain(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """串联执行计划中的用例，支持变量传递.

    流程：
        1. 按 order 顺序获取计划项
        2. 创建执行上下文 context = {}
        3. 对每个用例：
           a. 变量替换：将 ${var} 替换为 context 中的值（递归替换 url/headers/params/body）
           b. 执行用例（使用 test-engine 的 TestCaseExecutor）
           c. 变量提取：从响应中提取变量存入 context（使用 VariableExtractor）
           d. 失败策略判断：fail_strategy="stop" 时遇失败中断
        4. 返回结果 + 完整变量快照 context_snapshot
    """
    plan = _get_plan_or_404(db, plan_id)
    ensure_resource_role(db, current_user, plan, "tester")
    _sort_items(plan)

    context: dict[str, Any] = {}
    results: list[dict] = []
    passed = 0
    failed = 0
    run_id = str(uuid.uuid4())
    fail_strategy = plan.fail_strategy or "stop"

    for item in plan.items:
        case = item.test_case
        if case is None:
            # 用例已被删除，记录跳过
            results.append(
                {
                    "test_case_id": item.test_case_id,
                    "title": "(已删除)",
                    "order": item.order,
                    "status": "skipped",
                    "error": "用例不存在",
                }
            )
            failed += 1
            if fail_strategy == "stop":
                break
            continue

        if case.project_id != plan.project_id:
            raise ValidationError("测试计划包含其他项目的测试用例")
        ensure_resource_role(db, current_user, case, "tester", owner_field=None)

        try:
            request_def = _build_chain_request_def(case, context)
            assertions = _build_assertions_from_case(case)
            result = _chain_executor.execute(
                request_def=request_def,
                assertions=assertions,
                variables=context,
                test_case_id=case.id,
            )

            # 变量提取：从执行结果中合并到 context
            for var in result.extracted_variables:
                context[var.name] = var.value

            status = result.status
            if status == "passed":
                passed += 1
            else:
                failed += 1

            serialized = _serialize_chain_result(result)
            serialized["title"] = case.title
            serialized["order"] = item.order
            results.append(serialized)

            # 失败策略：stop 时遇失败中断
            if fail_strategy == "stop" and status != "passed":
                break
        except Exception as exc:  # noqa: BLE001 - 捕获执行异常以记录错误
            failed += 1
            results.append(
                {
                    "test_case_id": case.id,
                    "title": case.title,
                    "order": item.order,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            if fail_strategy == "stop":
                break

    return DataResponse(
        data=redact_sensitive_data(
            {
                "run_id": run_id,
                "results": results,
                "context_snapshot": context,
                "total": len(results),
                "passed": passed,
                "failed": failed,
            }
        )
    )
