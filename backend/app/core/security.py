"""认证与安全：JWT 令牌与密码哈希."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """对明文密码做哈希."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配."""
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str | dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """生成 JWT 访问令牌."""
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {"exp": expire}
    if isinstance(subject, str):
        payload["sub"] = subject
    else:
        payload.update(subject)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """解码并验证 JWT 令牌，返回 payload."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[ALGORITHM]
        )
        return payload
    except JWTError as exc:
        raise ValueError(f"无效的令牌: {exc}") from exc
