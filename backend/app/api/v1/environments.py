"""环境管理 CRUD API.

SEC-08 改造：所有响应均返回脱敏数据；密码与 Cookie 值加密落库。
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.sanitizer import sanitize_cookies, sanitize_db_config
from app.database import get_db
from app.models import Environment
from app.schemas.common import DataResponse, PageResponse
from app.schemas.environment import (
    EnvironmentCreate,
    EnvironmentDetailResponse,
    EnvironmentResponse,
    EnvironmentUpdate,
)
from app.services.security.secret_crypto import (
    SecretCryptoError,
    encrypt_cookies,
    encrypt_db_config,
)

router = APIRouter()


def _to_env_response(env) -> dict:
    """将 Environment ORM 对象转为不可泄密的响应字典."""
    return {
        "id": env.id,
        "name": env.name,
        "description": env.description,
        "base_url": env.base_url,
        "variables": dict(env.variables or {}),
        "db_config": sanitize_db_config(env.db_config),
        "cookies": sanitize_cookies(env.cookies),
        "is_active": env.is_active,
        "created_at": env.created_at,
        "updated_at": env.updated_at,
    }


def _cookie_identity(cookie: dict) -> tuple:
    return (
        cookie.get("name"),
        cookie.get("domain"),
        cookie.get("path", "/"),
    )


def _prepare_db_config(
    config: dict | None,
    existing: dict | None = None,
) -> dict | None:
    """Encrypt a database password and preserve a masked existing value."""
    if config is None:
        return None
    candidate = dict(config)
    candidate.pop("has_password", None)
    existing_password = existing.get("password") if existing else None
    if candidate.get("password") == "****":
        if existing_password:
            candidate["password"] = existing_password
        else:
            candidate.pop("password", None)
    elif "password" not in candidate and existing_password:
        candidate["password"] = existing_password
    return encrypt_db_config(candidate)


def _prepare_cookies(
    cookies: list[dict] | None,
    existing: list[dict] | None = None,
) -> list[dict]:
    """Encrypt Cookie values and preserve values represented by response masks."""
    existing_by_identity = {
        _cookie_identity(cookie): cookie for cookie in existing or []
    }
    candidates: list[dict] = []
    for cookie in cookies or []:
        candidate = dict(cookie)
        candidate.pop("has_value", None)
        previous = existing_by_identity.get(_cookie_identity(candidate))
        previous_value = previous.get("value") if previous else None
        if candidate.get("value") == "****":
            if previous_value:
                candidate["value"] = previous_value
            else:
                candidate.pop("value", None)
        elif "value" not in candidate and previous_value:
            candidate["value"] = previous_value
        candidates.append(candidate)
    return encrypt_cookies(candidates)


def _encrypt_environment_fields(
    data: dict,
    *,
    existing_db_config: dict | None = None,
    existing_cookies: list[dict] | None = None,
) -> dict:
    encrypted = dict(data)
    try:
        if "db_config" in encrypted:
            encrypted["db_config"] = _prepare_db_config(
                encrypted["db_config"],
                existing_db_config,
            )
        if "cookies" in encrypted:
            encrypted["cookies"] = _prepare_cookies(
                encrypted["cookies"],
                existing_cookies,
            )
    except (SecretCryptoError, TypeError) as exc:
        raise ValidationError(
            "敏感字段加密失败",
            detail=str(exc),
        ) from exc
    return encrypted


def validate_base_url(url: str) -> bool:
    """Validate an HTTP(S) URL with an IP address or DNS hostname."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or (port is not None and not 1 <= port <= 65535)
    ):
        return False

    host = parsed.hostname.rstrip(".")
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if host == "localhost":
        return True
    if len(host) > 253:
        return False
    labels = host.split(".")
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )


@router.get("", response_model=PageResponse[EnvironmentResponse])
def list_environments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: str | None = Query(None, description="按名称模糊搜索"),
    db: Session = Depends(get_db),
):
    """环境列表分页，支持按 name 搜索."""
    query = select(Environment)
    if name:
        query = query.where(Environment.name.ilike(f"%{name}%"))

    # 总数
    count_query = select(func.count()).select_from(Environment)
    if name:
        count_query = count_query.where(Environment.name.ilike(f"%{name}%"))
    total = db.execute(count_query).scalar_one()

    # 分页
    items = (
        db.execute(
            query.order_by(Environment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[EnvironmentResponse](
        data=[_to_env_response(e) for e in items], total=total, page=page, page_size=page_size
    )


@router.get("/{env_id}", response_model=DataResponse[EnvironmentDetailResponse])
def get_environment(env_id: str, db: Session = Depends(get_db)):
    """获取单个环境（敏感字段脱敏）."""
    env = db.get(Environment, env_id)
    if not env:
        raise NotFoundError("环境", env_id)
    return DataResponse[EnvironmentDetailResponse](data=_to_env_response(env))


@router.post("", response_model=DataResponse[EnvironmentDetailResponse])
def create_environment(
    payload: EnvironmentCreate, db: Session = Depends(get_db)
):
    """创建环境."""
    if not validate_base_url(payload.base_url):
        raise ValidationError(
            "base_url 必须是有效的 HTTP(S) 地址",
            detail={"base_url": payload.base_url},
        )
    data = _encrypt_environment_fields(payload.model_dump())
    env = Environment(**data)
    db.add(env)
    db.commit()
    db.refresh(env)
    return DataResponse[EnvironmentDetailResponse](data=_to_env_response(env))


@router.put("/{env_id}", response_model=DataResponse[EnvironmentDetailResponse])
def update_environment(
    env_id: str,
    payload: EnvironmentUpdate,
    db: Session = Depends(get_db),
):
    """更新环境（部分更新）。"""
    env = db.get(Environment, env_id)
    if not env:
        raise NotFoundError("环境", env_id)
    update_data = payload.model_dump(exclude_unset=True)
    # 如果更新了 base_url，需要校验 URL 格式
    if (
        "base_url" in update_data
        and update_data["base_url"] is not None
        and not validate_base_url(update_data["base_url"])
    ):
        raise ValidationError(
            "base_url 必须是有效的 HTTP(S) 地址",
            detail={"base_url": update_data["base_url"]},
        )
    update_data = _encrypt_environment_fields(
        update_data,
        existing_db_config=env.db_config,
        existing_cookies=env.cookies,
    )
    for field, value in update_data.items():
        setattr(env, field, value)
    db.commit()
    db.refresh(env)
    return DataResponse[EnvironmentDetailResponse](data=_to_env_response(env))


@router.delete("/{env_id}", response_model=DataResponse[EnvironmentDetailResponse])
def delete_environment(env_id: str, db: Session = Depends(get_db)):
    """删除环境."""
    env = db.get(Environment, env_id)
    if not env:
        raise NotFoundError("环境", env_id)
    data = _to_env_response(env)
    db.delete(env)
    db.commit()
    return DataResponse[EnvironmentDetailResponse](data=data)
