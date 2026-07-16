"""契约测试 API：创建契约、版本管理、差异对比、接口校验.

端点：
    POST /contracts                — 创建契约（首个版本）
    POST /contracts/{id}/versions  — 新增版本
    GET  /contracts/{id}/diff      — 版本差异对比
    POST /contracts/{id}/validate  — 校验接口是否符合契约
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.contract import ContractDiff, ContractVersion
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.schemas.contract import (
    ContractCreate,
    ContractDiffResponse,
    ContractValidateRequest,
    ContractVersionCreate,
    ContractVersionResponse,
)
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)

router = APIRouter()


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


def _to_version_response(cv: ContractVersion) -> ContractVersionResponse:
    """将 ContractVersion ORM 对象转为响应."""
    return ContractVersionResponse(
        id=cv.id,
        contract_id=cv.contract_id,
        name=cv.name,
        version=cv.version,
        openapi_spec=_parse_json(cv.openapi_spec, None),
        project_id=cv.project_id,
        status=cv.status,
        created_by=cv.created_by,
        created_at=cv.created_at,
    )


def _to_diff_response(diff: ContractDiff) -> ContractDiffResponse:
    """将 ContractDiff ORM 对象转为响应."""
    return ContractDiffResponse(
        id=diff.id,
        contract_id=diff.contract_id,
        from_version=diff.from_version,
        to_version=diff.to_version,
        breaking_changes=_parse_json(diff.breaking_changes, None),
        non_breaking_changes=_parse_json(diff.non_breaking_changes, None),
        affected_test_cases=_parse_json(diff.affected_test_cases, None),
        created_at=diff.created_at,
    )


def _get_versions(db: Session, contract_id: str) -> list[ContractVersion]:
    """按版本号升序获取指定契约的全部版本."""
    return (
        db.execute(
            select(ContractVersion)
            .where(ContractVersion.contract_id == contract_id)
            .order_by(ContractVersion.version.asc())
        )
        .scalars()
        .all()
    )


def _compute_diff(
    from_spec: dict[str, Any] | None,
    to_spec: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """对比两个 OpenAPI spec，返回 (破坏性变更, 非破坏性变更).

    简化实现：
    - 破坏性变更：删除已有路径、删除已有方法、必填参数新增、
      响应状态码被删除
    - 非破坏性变更：新增路径、新增方法、新增可选参数、新增响应状态码
    """
    breaking: list[dict[str, Any]] = []
    non_breaking: list[dict[str, Any]] = []
    from_spec = from_spec or {}
    to_spec = to_spec or {}
    from_paths = from_spec.get("paths", {}) or {}
    to_paths = to_spec.get("paths", {}) or {}

    # 路径删除 -> 破坏性
    for path, methods in from_paths.items():
        if path not in to_paths:
            breaking.append({"type": "path_removed", "path": path})
            continue
        # 方法删除 -> 破坏性
        for method in methods:
            if method not in (to_paths.get(path) or {}):
                breaking.append(
                    {"type": "method_removed", "path": path, "method": method}
                )

    # 路径/方法新增 -> 非破坏性
    for path, methods in to_paths.items():
        if path not in from_paths:
            non_breaking.append({"type": "path_added", "path": path})
            continue
        for method in methods:
            if method not in (from_paths.get(path) or {}):
                non_breaking.append(
                    {"type": "method_added", "path": path, "method": method}
                )

    return breaking, non_breaking


def _validate_against_spec(
    spec: dict[str, Any] | None,
    req: ContractValidateRequest,
) -> tuple[bool, list[dict[str, Any]]]:
    """校验实际接口是否符合契约 OpenAPI 规范.

    返回 (是否通过, 问题列表)。
    简化实现：检查路径/方法是否存在、响应状态码是否在契约定义范围内。
    """
    issues: list[dict[str, Any]] = []
    spec = spec or {}
    paths = spec.get("paths", {}) or {}
    path_item = paths.get(req.path)
    if not path_item:
        issues.append(
            {"type": "path_not_found", "message": f"路径 {req.path} 未在契约中定义"}
        )
        return False, issues
    method_lower = req.method.lower()
    operation = path_item.get(method_lower)
    if not operation:
        issues.append(
            {
                "type": "method_not_found",
                "message": f"方法 {req.method} 未在契约路径 {req.path} 中定义",
            }
        )
        return False, issues

    # 校验响应状态码
    if req.status_code is not None:
        responses = operation.get("responses", {}) or {}
        code_key = str(req.status_code)
        # 支持 2xx/3xx/4xx/5xx 通配
        wildcard = f"{req.status_code // 100}XX"
        if code_key not in responses and wildcard not in responses:
            issues.append(
                {
                    "type": "status_code_not_defined",
                    "message": f"状态码 {req.status_code} 未在契约中定义",
                }
            )

    return len(issues) == 0, issues


@router.get("", response_model=PageResponse[ContractVersionResponse])
def list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """契约版本列表（仅返回每个契约的 active 版本）."""
    query = select(ContractVersion).where(ContractVersion.status == "active")
    count_query = (
        select(func.count())
        .select_from(ContractVersion)
        .where(ContractVersion.status == "active")
    )
    if project_id:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(query, ContractVersion, current_user)
    count_query = scope_project_resources(
        count_query, ContractVersion, current_user
    )
    if project_id:
        query = query.where(ContractVersion.project_id == project_id)

    if project_id:
        count_query = count_query.where(ContractVersion.project_id == project_id)
    total = db.execute(count_query).scalar_one()

    items = (
        db.execute(
            query.order_by(ContractVersion.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[ContractVersionResponse](
        data=[_to_version_response(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DataResponse[ContractVersionResponse])
def create_contract(
    payload: ContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建契约并生成首个版本（version=1）."""
    import uuid

    ensure_project_assignment(
        db,
        current_user,
        payload.project_id,
        "developer",
        allow_unscoped_owner=True,
        unscoped_owner_id=current_user.id,
    )
    contract_id = str(uuid.uuid4())
    cv = ContractVersion(
        contract_id=contract_id,
        name=payload.name,
        version=1,
        openapi_spec=_dump_json(payload.openapi_spec),
        project_id=payload.project_id,
        status="active",
        created_by=current_user.id,
    )
    db.add(cv)
    db.commit()
    db.refresh(cv)
    return DataResponse[ContractVersionResponse](data=_to_version_response(cv))


@router.get("/{contract_id}/versions", response_model=DataResponse[list[ContractVersionResponse]])
def list_contract_versions(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出指定契约的全部版本."""
    versions = _get_versions(db, contract_id)
    if not versions:
        raise NotFoundError("契约", contract_id)
    ensure_resource_role(db, current_user, versions[0], "viewer")
    return DataResponse[list[ContractVersionResponse]](
        data=[_to_version_response(v) for v in versions]
    )


@router.post("/{contract_id}/versions", response_model=DataResponse[ContractVersionResponse])
def add_contract_version(
    contract_id: str,
    payload: ContractVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为契约新增版本：旧 active 版本置为 superseded，新版本为 active.

    新增版本时会自动计算与上一版本的差异并写入 ContractDiff。
    """
    versions = _get_versions(db, contract_id)
    if not versions:
        raise NotFoundError("契约", contract_id)

    latest = versions[-1]
    ensure_resource_role(db, current_user, versions[0], "developer")
    new_version_num = (latest.version or 1) + 1
    name = payload.name or latest.name

    # 旧版本置为 superseded
    latest.status = "superseded"

    new_cv = ContractVersion(
        contract_id=contract_id,
        name=name,
        version=new_version_num,
        openapi_spec=_dump_json(payload.openapi_spec),
        project_id=latest.project_id,
        status="active",
        created_by=current_user.id,
    )
    db.add(new_cv)
    db.flush()

    # 计算差异并持久化
    from_spec = _parse_json(latest.openapi_spec, None)
    to_spec = payload.openapi_spec
    breaking, non_breaking = _compute_diff(from_spec, to_spec)
    diff = ContractDiff(
        contract_id=contract_id,
        from_version=latest.version,
        to_version=new_version_num,
        breaking_changes=_dump_json(breaking) if breaking else None,
        non_breaking_changes=_dump_json(non_breaking) if non_breaking else None,
        affected_test_cases=None,
    )
    db.add(diff)
    db.commit()
    db.refresh(new_cv)
    return DataResponse[ContractVersionResponse](data=_to_version_response(new_cv))


@router.get("/{contract_id}/diff", response_model=DataResponse[list[ContractDiffResponse]])
def get_contract_diff(
    contract_id: str,
    from_version: int | None = Query(None, description="起始版本，默认最早"),
    to_version: int | None = Query(None, description="目标版本，默认最新"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询契约版本差异.

    不指定 from_version/to_version 时返回全部历史差异记录；
    指定时返回匹配的记录。
    """
    versions = _get_versions(db, contract_id)
    if not versions:
        raise NotFoundError("契约", contract_id)
    ensure_resource_role(db, current_user, versions[0], "viewer")

    stmt = select(ContractDiff).where(ContractDiff.contract_id == contract_id)
    if from_version is not None:
        stmt = stmt.where(ContractDiff.from_version == from_version)
    if to_version is not None:
        stmt = stmt.where(ContractDiff.to_version == to_version)
    stmt = stmt.order_by(ContractDiff.created_at.desc())

    diffs = db.execute(stmt).scalars().all()

    # 若无持久化差异但指定了两个版本，则实时计算
    if not diffs and from_version is not None and to_version is not None:
        from_cv = next((v for v in versions if v.version == from_version), None)
        to_cv = next((v for v in versions if v.version == to_version), None)
        if from_cv and to_cv:
            breaking, non_breaking = _compute_diff(
                _parse_json(from_cv.openapi_spec, None),
                _parse_json(to_cv.openapi_spec, None),
            )
            diffs = [
                ContractDiff(
                    id="",
                    contract_id=contract_id,
                    from_version=from_version,
                    to_version=to_version,
                    breaking_changes=_dump_json(breaking) if breaking else None,
                    non_breaking_changes=_dump_json(non_breaking) if non_breaking else None,
                    affected_test_cases=None,
                    created_at=None,
                )
            ]

    return DataResponse[list[ContractDiffResponse]](
        data=[_to_diff_response(d) for d in diffs]
    )


@router.post("/{contract_id}/validate", response_model=DataResponse[dict])
def validate_contract(
    contract_id: str,
    payload: ContractValidateRequest,
    version: int | None = Query(None, description="指定版本，默认最新 active 版本"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """校验实际接口是否符合契约定义."""
    versions = _get_versions(db, contract_id)
    if not versions:
        raise NotFoundError("契约", contract_id)
    ensure_resource_role(db, current_user, versions[0], "tester")

    if version is not None:
        target = next((v for v in versions if v.version == version), None)
        if not target:
            raise ValidationError(f"契约版本 {version} 不存在")
    else:
        # 取 active 版本（最新）
        target = next((v for v in reversed(versions) if v.status == "active"), None)
        if not target:
            target = versions[-1]

    spec = _parse_json(target.openapi_spec, None)
    passed, issues = _validate_against_spec(spec, payload)
    return DataResponse[dict](
        data={
            "contract_id": contract_id,
            "version": target.version,
            "passed": passed,
            "issues": issues,
        }
    )
