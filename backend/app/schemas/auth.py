"""认证与用户/角色 Schema."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 登录与令牌
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    """登录请求."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """登录成功返回的 JWT 令牌."""

    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


# ---------------------------------------------------------------------------
# 角色
# ---------------------------------------------------------------------------
class RoleCreate(BaseModel):
    """创建角色."""

    name: str = Field(..., max_length=64)
    description: str | None = Field(default=None, max_length=256)
    permissions: list[str] = Field(default_factory=list)
    is_active: bool = True


class RoleUpdate(BaseModel):
    """更新角色，全部字段可选."""

    name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=256)
    permissions: list[str] | None = None
    is_active: bool | None = None


class RoleResponse(BaseModel):
    """角色响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    permissions: list[str] = []
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    """创建用户（明文密码）."""

    username: str = Field(..., min_length=1, max_length=64)
    email: str = Field(..., max_length=128)
    password: str = Field(..., min_length=1, max_length=128)
    is_active: bool = True
    is_superuser: bool = False


class UserUpdate(BaseModel):
    """更新用户，全部字段可选."""

    username: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None
    is_superuser: bool | None = None


class UserResponse(BaseModel):
    """用户响应（不含密码）."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    is_active: bool = True
    is_superuser: bool = False
    roles: list[RoleResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AssignRolesRequest(BaseModel):
    """为用户分配角色（覆盖原有角色）."""

    role_ids: list[str] = []


# 解决 TokenResponse 中 UserResponse 的前向引用
TokenResponse.model_rebuild()
