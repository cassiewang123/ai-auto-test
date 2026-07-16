"""质量门禁 API：CRUD、评估、历史结果查询.

端点：
    GET    /quality-gates              — 列表
    POST   /quality-gates              — 创建
    PUT    /quality-gates/{id}         — 更新
    DELETE /quality-gates/{id}         — 删除
    POST   /quality-gates/{id}/evaluate — 评估门禁
    GET    /quality-gates/{id}/results — 查询历史结果
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.quality_gate import QualityGate, QualityGateResult
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.schemas.quality_gate import (
    QualityGateCreate,
    QualityGateEvaluateRequest,
    QualityGateResponse,
    QualityGateResultResponse,
    QualityGateUpdate,
)
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)

router = APIRouter()

_VALID_MODES = {"block", "warn", "log"}


def _parse_json(raw: str | None, default: Any) -> Any:
    """将 Text 中存储的 JSON 字符串解析为 Python 对象."""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


def _dump_json(value: Any) -> str:
    """将 Python 对象序列化为 JSON 字符串以存入 Text 字段."""
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _to_gate_response(gate: QualityGate) -> QualityGateResponse:
    """将 QualityGate ORM 对象转为响应."""
    return QualityGateResponse(
        id=gate.id,
        name=gate.name,
        project_id=gate.project_id,
        rules=_parse_json(gate.rules, None),
        mode=gate.mode,
        is_active=gate.is_active,
        created_at=gate.created_at,
        updated_at=gate.updated_at,
    )


def _to_result_response(result: QualityGateResult) -> QualityGateResultResponse:
    """将 QualityGateResult ORM 对象转为响应."""
    return QualityGateResultResponse(
        id=result.id,
        gate_id=result.gate_id,
        project_id=result.project_id,
        run_id=result.run_id,
        passed=result.passed,
        results=_parse_json(result.results, None),
        triggered_by=result.triggered_by,
        created_at=result.created_at,
    )


def _evaluate_rules(
    rules: list[dict[str, Any]] | None,
    metrics: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """评估门禁规则，返回 (是否全部通过, 各规则评估结果).

    规则结构示例：
        {"metric": "pass_rate", "op": ">=", "threshold": 0.9}
    支持的比较运算符：>=, >, <=, <, ==, !=。
    metrics 为实际指标值字典，如 {"pass_rate": 0.95, "coverage": 0.8}。
    """
    rule_results: list[dict[str, Any]] = []
    all_passed = True
    rules = rules or []

    op_funcs = {
        ">=": lambda a, b: a >= b,
        ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        "<": lambda a, b: a < b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
    }

    for rule in rules:
        metric = rule.get("metric")
        op = rule.get("op", ">=")
        threshold = rule.get("threshold")
        actual = metrics.get(metric) if metric else None

        passed = False
        if actual is None:
            # 指标缺失视为未通过
            reason = f"指标 '{metric}' 缺失"
        elif op not in op_funcs:
            reason = f"不支持的运算符 '{op}'"
        else:
            try:
                passed = op_funcs[op](actual, threshold)
                reason = (
                    f"{metric}={actual} {op} {threshold}: "
                    f"{'通过' if passed else '未通过'}"
                )
            except TypeError:
                passed = False
                reason = f"指标 '{metric}' 类型不匹配：{actual} {op} {threshold}"

        if not passed:
            all_passed = False
        rule_results.append(
            {
                "metric": metric,
                "op": op,
                "threshold": threshold,
                "actual": actual,
                "passed": passed,
                "reason": reason,
            }
        )

    return all_passed, rule_results


@router.get("", response_model=PageResponse[QualityGateResponse])
def list_quality_gates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    is_active: bool | None = Query(None, description="按启用状态筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """质量门禁列表分页."""
    query = select(QualityGate)
    count_query = select(func.count()).select_from(QualityGate)
    if project_id:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query, QualityGate, current_user, owner_field=None
    )
    count_query = scope_project_resources(
        count_query, QualityGate, current_user, owner_field=None
    )
    if project_id:
        query = query.where(QualityGate.project_id == project_id)
    if is_active is not None:
        query = query.where(QualityGate.is_active == is_active)

    if project_id:
        count_query = count_query.where(QualityGate.project_id == project_id)
    if is_active is not None:
        count_query = count_query.where(QualityGate.is_active == is_active)
    total = db.execute(count_query).scalar_one()

    items = (
        db.execute(
            query.order_by(QualityGate.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[QualityGateResponse](
        data=[_to_gate_response(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DataResponse[QualityGateResponse])
def create_quality_gate(
    payload: QualityGateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建质量门禁."""
    ensure_project_assignment(db, current_user, payload.project_id, "developer")
    if payload.mode and payload.mode not in _VALID_MODES:
        raise ValidationError(
            f"非法门禁模式，可选: {','.join(sorted(_VALID_MODES))}"
        )
    gate = QualityGate(
        name=payload.name,
        project_id=payload.project_id,
        rules=_dump_json(payload.rules),
        mode=payload.mode or "block",
        is_active=payload.is_active if payload.is_active is not None else True,
    )
    db.add(gate)
    db.commit()
    db.refresh(gate)
    return DataResponse[QualityGateResponse](data=_to_gate_response(gate))


@router.put("/{gate_id}", response_model=DataResponse[QualityGateResponse])
def update_quality_gate(
    gate_id: str,
    payload: QualityGateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新质量门禁（部分更新）."""
    gate = db.get(QualityGate, gate_id)
    if not gate:
        raise NotFoundError("质量门禁", gate_id)
    ensure_resource_role(
        db, current_user, gate, "developer", owner_field=None
    )
    update_data = payload.model_dump(exclude_unset=True)
    if "mode" in update_data or "is_active" in update_data:
        ensure_resource_role(
            db, current_user, gate, "admin", owner_field=None
        )
    if "project_id" in update_data and update_data["project_id"] != gate.project_id:
        ensure_resource_role(
            db, current_user, gate, "admin", owner_field=None
        )
        ensure_project_assignment(
            db, current_user, update_data["project_id"], "admin"
        )
    if (
        "mode" in update_data
        and update_data["mode"] is not None
        and update_data["mode"] not in _VALID_MODES
    ):
        raise ValidationError(
            f"非法门禁模式，可选: {','.join(sorted(_VALID_MODES))}"
        )
    if "rules" in update_data:
        gate.rules = _dump_json(update_data.pop("rules"))
    for field, value in update_data.items():
        setattr(gate, field, value)
    db.commit()
    db.refresh(gate)
    return DataResponse[QualityGateResponse](data=_to_gate_response(gate))


@router.delete("/{gate_id}", response_model=DataResponse[QualityGateResponse])
def delete_quality_gate(
    gate_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除质量门禁."""
    gate = db.get(QualityGate, gate_id)
    if not gate:
        raise NotFoundError("质量门禁", gate_id)
    ensure_resource_role(db, current_user, gate, "admin", owner_field=None)
    resp = _to_gate_response(gate)
    db.delete(gate)
    db.commit()
    return DataResponse[QualityGateResponse](data=resp)


@router.post("/{gate_id}/evaluate", response_model=DataResponse[QualityGateResultResponse])
def evaluate_quality_gate(
    gate_id: str,
    payload: QualityGateEvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """评估质量门禁：对给定 metrics 执行规则匹配并持久化结果."""
    gate = db.get(QualityGate, gate_id)
    if not gate:
        raise NotFoundError("质量门禁", gate_id)
    ensure_resource_role(db, current_user, gate, "tester", owner_field=None)
    if not gate.is_active:
        raise ValidationError("质量门禁已停用，无法评估")
    if payload.project_id and payload.project_id != gate.project_id:
        raise ValidationError("Evaluation project must match the quality gate project")

    rules = _parse_json(gate.rules, None)
    passed, rule_results = _evaluate_rules(rules, payload.metrics)

    result = QualityGateResult(
        gate_id=gate.id,
        project_id=payload.project_id or gate.project_id,
        run_id=payload.run_id,
        passed=passed,
        results=_dump_json(rule_results),
        triggered_by=current_user.id,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return DataResponse[QualityGateResultResponse](data=_to_result_response(result))


@router.get("/{gate_id}/results", response_model=PageResponse[QualityGateResultResponse])
def list_quality_gate_results(
    gate_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    passed: bool | None = Query(None, description="按是否通过筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询质量门禁的历史评估结果."""
    gate = db.get(QualityGate, gate_id)
    if not gate:
        raise NotFoundError("质量门禁", gate_id)
    ensure_resource_role(db, current_user, gate, "viewer", owner_field=None)

    query = select(QualityGateResult).where(QualityGateResult.gate_id == gate_id)
    count_query = (
        select(func.count())
        .select_from(QualityGateResult)
        .where(QualityGateResult.gate_id == gate_id)
    )
    if passed is not None:
        query = query.where(QualityGateResult.passed == passed)
        count_query = count_query.where(QualityGateResult.passed == passed)

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(QualityGateResult.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[QualityGateResultResponse](
        data=[_to_result_response(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )
