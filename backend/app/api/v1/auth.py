"""认证 API：登录、注册、获取当前用户."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.security import hash_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserResponse
from app.schemas.common import DataResponse
from app.services.auth_service import (
    authenticate_user,
    build_user_response,
    create_user_token,
    get_current_user,
    is_first_user,
)

router = APIRouter()


@router.post("/login", response_model=DataResponse[TokenResponse])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """用户名 + 密码登录，返回 JWT 令牌."""
    user = authenticate_user(db, payload.username, payload.password)
    token = create_user_token(user)
    return DataResponse[TokenResponse](
        data=TokenResponse(
            access_token=token,
            token_type="bearer",
            user=build_user_response(user, db),
        )
    )


@router.get("/me", response_model=DataResponse[UserResponse])
def get_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前登录用户信息."""
    return DataResponse[UserResponse](data=build_user_response(current_user, db))


@router.post("/register", response_model=DataResponse[UserResponse])
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """注册新用户；首个用户自动成为超级管理员。"""
    exists = db.execute(
        select(User).where(
            (User.username == payload.username)
            | (User.email == payload.email)
        )
    ).scalar_one_or_none()
    if exists:
        raise ValidationError("用户名或邮箱已存在")

    first = is_first_user(db)
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_active=payload.is_active,
        # 注册接口不允许显式指定超级管理员，仅首个用户自动获得
        is_superuser=first,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return DataResponse[UserResponse](data=build_user_response(user, db))
