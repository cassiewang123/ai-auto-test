"""用户管理 API（需要 user:manage 权限）."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import hash_password
from app.database import get_db
from app.models.role import Role, user_role
from app.models.user import User
from app.schemas.auth import (
    AssignRolesRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.schemas.common import DataResponse, PageResponse
from app.services.auth_service import build_user_response, require_permission

router = APIRouter()


def _get_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("用户", user_id)
    return user


@router.get("", response_model=PageResponse[UserResponse])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("user:manage")),
):
    """用户列表分页，支持按用户名/邮箱搜索。"""
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if keyword:
        like = f"%{keyword}%"
        cond = or_(User.username.like(like), User.email.like(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = db.execute(count_stmt).scalar_one()
    items = (
        db.execute(
            stmt.order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[UserResponse](
        data=[build_user_response(u, db) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DataResponse[UserResponse])
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("user:manage")),
):
    """创建用户。"""
    exists = db.execute(
        select(User).where(
            or_(User.username == payload.username, User.email == payload.email)
        )
    ).scalar_one_or_none()
    if exists:
        raise ValidationError("用户名或邮箱已存在")
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_active=payload.is_active,
        is_superuser=payload.is_superuser,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return DataResponse[UserResponse](data=build_user_response(user, db))


@router.put("/{user_id}", response_model=DataResponse[UserResponse])
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("user:manage")),
):
    """更新用户信息；若提供 password 则重新哈希。"""
    user = _get_or_404(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for field, value in data.items():
        setattr(user, field, value)
    if password:
        user.hashed_password = hash_password(password)
    db.commit()
    db.refresh(user)
    return DataResponse[UserResponse](data=build_user_response(user, db))


@router.delete("/{user_id}", response_model=DataResponse[UserResponse])
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("user:manage")),
):
    """删除用户。"""
    user = _get_or_404(db, user_id)
    # 清理多对多关联，避免外键残留
    db.execute(delete(user_role).where(user_role.c.user_id == user_id))
    data = build_user_response(user, db)
    db.delete(user)
    db.commit()
    return DataResponse[UserResponse](data=data)


@router.post("/{user_id}/roles", response_model=DataResponse[UserResponse])
def assign_roles(
    user_id: str,
    payload: AssignRolesRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("user:manage")),
):
    """为用户分配角色（覆盖原有角色）。"""
    user = _get_or_404(db, user_id)
    # 先清除原有关联
    db.execute(delete(user_role).where(user_role.c.user_id == user_id))
    if payload.role_ids:
        roles = (
            db.execute(select(Role).where(Role.id.in_(payload.role_ids)))
            .scalars()
            .all()
        )
        if len(roles) != len(set(payload.role_ids)):
            raise ValidationError("部分角色 ID 不存在")
        # 批量插入新关联
        db.execute(
            insert(user_role),
            [{"user_id": user_id, "role_id": rid} for rid in payload.role_ids],
        )
    db.commit()
    db.refresh(user)
    return DataResponse[UserResponse](data=build_user_response(user, db))
