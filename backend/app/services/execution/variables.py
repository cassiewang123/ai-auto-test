"""执行期变量加载与合并.

变量优先级（由低到高）：
    全局变量 -> 工作空间变量 -> 环境变量 -> 调用方传入的临时变量

所有执行入口（单条执行、批量执行、异步任务、定时任务、数据驱动、性能场景）都应
通过本模块加载变量，避免出现"用例里写了 {{变量}} 却没有渲染"的问题。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session


def cast_variable(value: str | None, var_type: str) -> Any:
    """按变量类型转换字符串值为对应 Python 类型."""
    if value is None:
        return ""
    try:
        if var_type == "number":
            if "." in str(value):
                return float(value)
            return int(value)
        if var_type == "boolean":
            return str(value).lower() in ("true", "1", "yes")
        if var_type == "json":
            return json.loads(value)
    except (ValueError, TypeError):
        pass
    return value


def load_global_variables(
    db: Session, project_id: str | None = None
) -> dict[str, Any]:
    """加载全局变量与指定项目的工作空间变量，返回变量字典."""
    from app.models import GlobalVariable

    query = db.query(GlobalVariable)
    if project_id:
        from sqlalchemy import or_

        query = query.filter(
            or_(
                GlobalVariable.scope == "global",
                GlobalVariable.project_id == project_id,
            )
        )
    else:
        query = query.filter(GlobalVariable.scope == "global")

    variables: dict[str, Any] = {}
    for var in query.all():
        variables[var.name] = cast_variable(var.value, var.var_type)
    return variables


def load_case_variables(
    db: Session, case, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """加载用例执行所需的完整变量池（含环境变量覆盖）."""
    variables = load_global_variables(db, getattr(case, "project_id", None))
    environment_id = getattr(case, "environment_id", None)
    if environment_id:
        from app.models.environment import Environment

        env = db.get(Environment, environment_id)
        if env:
            variables.update(env.variables or {})
    if extra:
        variables.update(extra)
    return variables


def load_environment_context(
    db: Session, case
) -> tuple[dict[str, Any], list[dict], str | None]:
    """加载用例的环境变量、Cookie 与 base_url.

    Returns:
        (环境变量, 环境 Cookie, base_url)
    """
    environment_id = getattr(case, "environment_id", None)
    if not environment_id:
        return {}, [], None

    from app.models.environment import Environment
    from app.services.security.secret_crypto import (
        SecretCryptoError,
        decrypt_cookies,
    )

    env = db.get(Environment, environment_id)
    if not env:
        return {}, [], None
    try:
        cookies = decrypt_cookies(env.cookies)
    except (SecretCryptoError, TypeError):
        cookies = []
    return dict(env.variables or {}), cookies, env.base_url
