"""认证服务：JWT 令牌生成/验证、用户认证、RBAC 权限检查.

复用 app.core.security 中的密码哈希与 JWT 编解码能力，
在此之上提供 FastAPI 依赖注入函数（get_current_user / require_permission）。

注意：User 与 Role 之间不使用 ORM relationship，而是通过 user_role 关联表
以 SQLAlchemy Core 直接查询，避免 User mapper 初始化依赖 role 模块的导入顺序。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, ForbiddenError, NotFoundError
from app.core.security import (
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.database import get_db
from app.models.role import Role, user_role
from app.models.user import User
from app.schemas.auth import RoleResponse, UserResponse

# OAuth2 令牌提取器：从 Authorization: Bearer <token> 中读取
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login", auto_error=False
)


def authenticate_user(db: Session, username: str, password: str) -> User:
    """校验用户名与密码，返回用户对象；失败抛出 AuthenticationError."""
    user = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise AuthenticationError("用户名或密码错误")
    if not user.is_active:
        raise AuthenticationError("用户已被禁用")
    return user


def create_user_token(user: User) -> str:
    """为用户生成 JWT 令牌，payload 含 sub/username/is_superuser/exp."""
    return create_access_token(
        {
            "sub": user.id,
            "username": user.username,
            "is_superuser": user.is_superuser,
        }
    )


def get_user_roles(user: User, db: Session) -> list[Role]:
    """通过 user_role 关联表查询用户拥有的全部角色。"""
    return list(
        db.execute(
            select(Role)
            .join(user_role, user_role.c.role_id == Role.id)
            .where(user_role.c.user_id == user.id)
        )
        .scalars()
        .all()
    )


def get_user_permissions(user: User, db: Session) -> set[str]:
    """获取用户聚合后的权限集合。

    超级用户拥有全部权限（以 "*" 表示）；普通用户为其所有启用角色权限的并集。
    """
    if user.is_superuser:
        return {"*"}
    perms: set[str] = set()
    for role in get_user_roles(user, db):
        if role.is_active and role.permissions:
            perms.update(role.permissions)
    return perms


def build_user_response(user: User, db: Session) -> UserResponse:
    """构造 UserResponse，手动查询并填充角色列表。"""
    resp = UserResponse.model_validate(user)
    roles = get_user_roles(user, db)
    resp.roles = [RoleResponse.model_validate(r) for r in roles]
    return resp


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI 依赖：从令牌解析当前登录用户。"""
    credentials_exception = AuthenticationError("无法验证凭证")
    if not token:
        raise credentials_exception
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise AuthenticationError("无效或过期的令牌") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception
    user = db.get(User, user_id)
    if not user:
        raise AuthenticationError("用户不存在")
    if not user.is_active:
        raise AuthenticationError("用户已被禁用")
    return user


def require_permission(permission: str) -> Callable[..., User]:
    """依赖工厂：要求当前用户具备指定权限（超级用户自动放行）。"""

    def _checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if user.is_superuser:
            return user
        perms = get_user_permissions(user, db)
        if permission in perms or "*" in perms:
            return user
        raise ForbiddenError(f"缺少权限: {permission}")

    return _checker


def require_superuser(user: User = Depends(get_current_user)) -> User:
    """依赖：要求当前用户为超级管理员。"""
    if not user.is_superuser:
        raise ForbiddenError("需要超级管理员权限")
    return user


def require_project_access(
    minimum_role: str = "viewer",
) -> Callable[..., Any]:
    """依赖工厂：按 project_members 校验项目角色."""

    async def _checker(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # 从路径参数、查询参数或请求体中提取 project_id
        project_id = request.path_params.get("project_id") or request.query_params.get(
            "project_id"
        )
        if not project_id:
            # 尝试从请求体获取（POST/PUT）
            try:
                body = await request.json()
                if isinstance(body, dict):
                    project_id = body.get("project_id")
            except Exception:
                pass
        if project_id:
            from app.services.project_access import ensure_project_role

            ensure_project_role(db, user, project_id, minimum_role)
        return user

    return _checker


def require_case_access(
    minimum_role: str = "viewer",
) -> Callable[..., Any]:
    """依赖工厂：基于路径参数 case_id 校验用户对该用例所属项目的访问权限.

    流程：
        1) 从路径参数提取 case_id
        2) 查询 TestCase.project_id
        3) 复用 require_project_access 的项目维度校验逻辑

    若 case 不存在则抛出 NotFoundError；无 project_id 的用例仅做权限校验。
    """

    async def _checker(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if user.is_superuser:
            return user
        case_id = request.path_params.get("case_id")
        project_id: str | None = None
        if case_id:
            # 延迟导入避免循环依赖
            from app.models.test_case import TestCase

            case = db.execute(
                select(TestCase).where(TestCase.id == case_id)
            ).scalar_one_or_none()
            if not case:
                raise NotFoundError("TestCase", case_id)
            project_id = case.project_id
        if project_id:
            from app.services.project_access import ensure_project_role

            ensure_project_role(db, user, project_id, minimum_role)
        return user

    return _checker


def is_first_user(db: Session) -> bool:
    """判断当前是否尚无任何用户（用于注册时自动赋予超级管理员）。"""
    count = db.execute(select(func.count()).select_from(User)).scalar_one()
    return count == 0
