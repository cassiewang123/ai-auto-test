"""接口分组管理 API.

端点：
    GET    /api-groups              — 分组列表（含由接口 group_path 推导出的分组）
    POST   /api-groups              — 新建分组
    PUT    /api-groups/{id}         — 编辑分组（改名同步更新其下接口的 group_path）
    DELETE /api-groups/{id}         — 删除分组（其下接口移动到上级分组）

说明：接口用例通过 ``TestCase.group_path`` 归组。接口导入后即使没有显式建组，
本接口也会把题库中出现的 group_path 及其所有父级路径一并返回，保证下拉与
目录树能完整展示现有模块；显式建组用于预先建立空分组或维护说明。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.api_group import ApiGroup
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.api_group import (
    ApiGroupCreate,
    ApiGroupDeleteResult,
    ApiGroupListResponse,
    ApiGroupResponse,
    ApiGroupUpdate,
)
from app.schemas.common import DataResponse
from app.services.auth_service import get_current_user

router = APIRouter()


def _normalize_path(value: str | None) -> str:
    """规范化分组路径：去空白、去首尾/重复斜杠."""
    parts = [part.strip() for part in (value or "").split("/")]
    return "/".join(part for part in parts if part)


def _leaf_name(path: str) -> str:
    return path.rsplit("/", 1)[-1] if path else ""


def _parent_path(path: str) -> str | None:
    return path.rsplit("/", 1)[0] if "/" in path else None


def _group_or_404(db: Session, group_id: str) -> ApiGroup:
    item = db.get(ApiGroup, group_id)
    if not item:
        raise NotFoundError("接口分组", group_id)
    return item


def _case_group_counts(db: Session, project_id: str | None) -> dict[str, int]:
    """统计各 group_path 的直接接口数量."""
    query = (
        select(TestCase.group_path, func.count())
        .where(TestCase.group_path.is_not(None), TestCase.group_path != "")
        .group_by(TestCase.group_path)
    )
    if project_id:
        query = query.where(TestCase.project_id == project_id)
    return {
        _normalize_path(path): int(count)
        for path, count in db.execute(query).all()
        if path
    }


def _contains_path(candidate: str, group_path: str) -> bool:
    """判断 candidate 是否属于 group_path（含自身与子分组）."""
    return candidate == group_path or candidate.startswith(f"{group_path}/")


def _build_response(
    group: ApiGroup | None,
    path: str,
    counts: dict[str, int],
) -> ApiGroupResponse:
    total = sum(
        count for case_path, count in counts.items() if _contains_path(case_path, path)
    )
    if group is not None:
        return ApiGroupResponse(
            id=group.id,
            path=group.path,
            name=group.name,
            parent_path=group.parent_path,
            description=group.description,
            sort_order=group.sort_order,
            project_id=group.project_id,
            case_count=total,
            derived=False,
            created_at=group.created_at,
            updated_at=group.updated_at,
        )
    return ApiGroupResponse(
        # 推导分组的 ID 使用路径，前端可据此区分为只读派生分组
        id=f"derived::{path}",
        path=path,
        name=_leaf_name(path),
        parent_path=_parent_path(path),
        description=None,
        sort_order=0,
        project_id=None,
        case_count=total,
        derived=True,
    )


def _collect_all_group_paths(
    db: Session, project_id: str | None
) -> tuple[dict[str, ApiGroup], set[str]]:
    """汇总显式分组与接口推导分组（含全部父级路径）."""
    group_query = select(ApiGroup)
    if project_id:
        group_query = group_query.where(ApiGroup.project_id == project_id)
    explicit = {
        group.path: group
        for group in db.execute(group_query).scalars().all()
    }

    paths: set[str] = set(explicit.keys())
    case_paths = _case_group_counts(db, project_id)
    for case_path in case_paths:
        parts = case_path.split("/")
        for index in range(1, len(parts) + 1):
            paths.add("/".join(parts[:index]))
    return explicit, paths


@router.get("", response_model=ApiGroupListResponse)
def list_groups(
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """分组列表：显式分组 + 由接口 group_path 推导出的分组."""
    explicit, paths = _collect_all_group_paths(db, project_id)
    counts = _case_group_counts(db, project_id)

    groups = [
        _build_response(explicit.get(path), path, counts)
        for path in paths
    ]
    # 顶级模块在前，同级按名称排序；有显式排序值的优先
    groups.sort(
        key=lambda item: (
            item.sort_order,
            item.path.count("/"),
            item.path,
        )
    )
    return ApiGroupListResponse(groups=groups, total=len(groups))


@router.post("", response_model=DataResponse[ApiGroupResponse])
def create_group(
    payload: ApiGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建分组."""
    name = _normalize_path(payload.name)
    if not name or "/" in name:
        raise ValidationError("分组名称不能为空且不能包含斜杠，请用上级分组表达层级")
    parent = _normalize_path(payload.parent_path) if payload.parent_path else None
    _, paths = _collect_all_group_paths(db, payload.project_id)
    if parent and parent not in paths:
        raise NotFoundError("上级分组", parent)

    path = f"{parent}/{name}" if parent else name
    existing = db.execute(
        select(ApiGroup).where(
            ApiGroup.path == path,
            ApiGroup.project_id == payload.project_id if payload.project_id else ApiGroup.project_id.is_(None),
        )
    ).scalars().first()
    if existing:
        raise ValidationError(f"分组已存在: {path}")

    group = ApiGroup(
        path=path,
        name=name,
        parent_path=parent,
        description=payload.description,
        sort_order=payload.sort_order,
        project_id=payload.project_id,
        created_by=current_user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    counts = _case_group_counts(db, payload.project_id)
    return DataResponse[ApiGroupResponse](
        data=_build_response(group, path, counts)
    )


def _rename_cases(
    db: Session, old_path: str, new_path: str, project_id: str | None
) -> int:
    """把 group_path 在 old_path 下的接口（含子分组）同步改到 new_path."""
    query = select(TestCase).where(TestCase.group_path.is_not(None))
    if project_id:
        query = query.where(TestCase.project_id == project_id)
    cases = db.execute(query).scalars().all()

    updated = 0
    for case in cases:
        current = _normalize_path(case.group_path)
        if not _contains_path(current, old_path):
            continue
        suffix = current[len(old_path):]
        case.group_path = f"{new_path}{suffix}" if suffix else new_path
        updated += 1
    return updated


def _rename_child_groups(
    db: Session, old_path: str, new_path: str, project_id: str | None
) -> None:
    """同步重命名已登记的子分组."""
    query = select(ApiGroup)
    if project_id:
        query = query.where(ApiGroup.project_id == project_id)
    for group in db.execute(query).scalars().all():
        if not _contains_path(group.path, old_path):
            continue
        suffix = group.path[len(old_path):]
        group.path = f"{new_path}{suffix}" if suffix else new_path
        group.name = _leaf_name(group.path)
        group.parent_path = _parent_path(group.path)


@router.put("/{group_id}", response_model=DataResponse[ApiGroupResponse])
def update_group(
    group_id: str,
    payload: ApiGroupUpdate,
    db: Session = Depends(get_db),
):
    """编辑分组；修改名称或上级分组时同步更新其下所有接口的 group_path.

    仅显式登记的分组可编辑；由接口推导出的分组请先新建为正式分组
    （前端「编辑分组」会引导完成这一步）。
    """
    group = _group_or_404(db, group_id)

    old_path = group.path
    name = group.name
    parent = group.parent_path

    if payload.name is not None:
        normalized = _normalize_path(payload.name)
        if not normalized or "/" in normalized:
            raise ValidationError(
                "分组名称不能为空且不能包含斜杠，请用上级分组表达层级"
            )
        name = normalized
    if payload.parent_path is not None:
        parent = _normalize_path(payload.parent_path) or None

    new_path = f"{parent}/{name}" if parent else name
    if new_path != old_path:
        if new_path.startswith(f"{old_path}/"):
            raise ValidationError("不能把分组移动到自己的子分组下")
        duplicate = db.execute(
            select(ApiGroup).where(
                ApiGroup.path == new_path,
                ApiGroup.project_id == group.project_id
                if group.project_id
                else ApiGroup.project_id.is_(None),
                ApiGroup.id != group.id,
            )
        ).scalars().first()
        if duplicate:
            raise ValidationError(f"分组已存在: {new_path}")

        _rename_cases(db, old_path, new_path, group.project_id)
        _rename_child_groups(db, old_path, new_path, group.project_id)
        group.path = new_path
        group.name = name
        group.parent_path = parent

    if payload.description is not None:
        group.description = payload.description
    if payload.sort_order is not None:
        group.sort_order = payload.sort_order

    db.commit()
    db.refresh(group)

    counts = _case_group_counts(db, group.project_id)
    return DataResponse[ApiGroupResponse](
        data=_build_response(group, group.path, counts)
    )


@router.delete("/{group_id}", response_model=DataResponse[ApiGroupDeleteResult])
def delete_group(group_id: str, db: Session = Depends(get_db)):
    """删除分组；其下接口与子分组移动到上级分组，避免接口丢失分组信息."""
    group = _group_or_404(db, group_id)
    parent = group.parent_path or None

    moved = _move_cases_to_parent(db, group.path, parent, group.project_id)
    _move_child_groups_to_parent(db, group.path, parent, group.project_id)

    db.delete(group)
    db.commit()
    return DataResponse[ApiGroupDeleteResult](
        data=ApiGroupDeleteResult(deleted=True, moved_cases=moved)
    )


def _move_cases_to_parent(
    db: Session, old_path: str, parent: str | None, project_id: str | None
) -> int:
    query = select(TestCase).where(TestCase.group_path.is_not(None))
    if project_id:
        query = query.where(TestCase.project_id == project_id)
    moved = 0
    for case in db.execute(query).scalars().all():
        current = _normalize_path(case.group_path)
        if not _contains_path(current, old_path):
            continue
        suffix = current[len(old_path):].lstrip("/")
        if parent:
            case.group_path = f"{parent}/{suffix}" if suffix else parent
        else:
            case.group_path = suffix or None
        moved += 1
    return moved


def _move_child_groups_to_parent(
    db: Session, old_path: str, parent: str | None, project_id: str | None
) -> None:
    query = select(ApiGroup)
    if project_id:
        query = query.where(ApiGroup.project_id == project_id)
    for group in db.execute(query).scalars().all():
        if group.path == old_path or not _contains_path(group.path, old_path):
            continue
        suffix = group.path[len(old_path):].lstrip("/")
        if parent:
            group.path = f"{parent}/{suffix}" if suffix else parent
        else:
            group.path = suffix
        group.name = _leaf_name(group.path)
        group.parent_path = _parent_path(group.path)
