"""角色管理 API（RBAC）."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.role import Role, user_role
from app.models.user import User
from app.schemas.auth import RoleCreate, RoleResponse, RoleUpdate
from app.schemas.common import DataResponse, PageResponse
from app.services.auth_service import require_permission

router = APIRouter()


def _get_or_404(db: Session, role_id: str) -> Role:
    role = db.get(Role, role_id)
    if not role:
        raise NotFoundError("角色", role_id)
    return role


@router.get("", response_model=PageResponse[RoleResponse])
def list_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:read")),
):
    """角色列表分页。"""
    stmt = select(Role)
    count_stmt = select(func.count(Role.id))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Role.name.like(like))
        count_stmt = count_stmt.where(Role.name.like(like))
    total = db.execute(count_stmt).scalar_one()
    items = (
        db.execute(
            stmt.order_by(Role.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[RoleResponse](
        data=items, total=total, page=page, page_size=page_size
    )


@router.get("/all", response_model=DataResponse[list[RoleResponse]])
def list_all_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:read")),
):
    """获取所有角色（不分页，用于下拉选择器）。"""
    items = db.execute(select(Role).order_by(Role.name)).scalars().all()
    return DataResponse(data=items)


@router.post("", response_model=DataResponse[RoleResponse])
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:manage")),
):
    """创建角色。"""
    exists = db.execute(
        select(Role).where(Role.name == payload.name)
    ).scalar_one_or_none()
    if exists:
        raise ValidationError("角色名称已存在")
    role = Role(**payload.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return DataResponse[RoleResponse](data=role)


@router.get("/{role_id}", response_model=DataResponse[RoleResponse])
def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:read")),
):
    """获取角色详情。"""
    return DataResponse[RoleResponse](data=_get_or_404(db, role_id))


@router.put("/{role_id}", response_model=DataResponse[RoleResponse])
def update_role(
    role_id: str,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:manage")),
):
    """更新角色。"""
    role = _get_or_404(db, role_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(role, field, value)
    db.commit()
    db.refresh(role)
    return DataResponse[RoleResponse](data=role)


@router.delete("/{role_id}", response_model=DataResponse[RoleResponse])
def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:manage")),
):
    """删除角色。"""
    role = _get_or_404(db, role_id)
    # 解除与用户的关联，避免外键残留
    db.execute(delete(user_role).where(user_role.c.role_id == role_id))
    data = RoleResponse.model_validate(role)
    db.delete(role)
    db.commit()
    return DataResponse[RoleResponse](data=data)
