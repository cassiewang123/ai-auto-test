"""数据库断言 CRUD API.

SEC-07 改造：
- 使用 sqlglot AST 校验 SQL，仅允许只读 SELECT
- 变量从字符串拼接改为 SQLAlchemy 参数绑定（:var 占位符），防止注入
- 自动添加 LIMIT 1000 行数限额
SEC-09 改造：
- 执行 SQL 断言时写入审计日志
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.db_assertion import DbAssertion
from app.models.environment import Environment
from app.models.user import User
from app.schemas.common import DataResponse, ResponseBase
from app.schemas.db_assertion import (
    DbAssertionCreate,
    DbAssertionResponse,
    DbAssertionUpdate,
)
from app.services.auth_service import get_current_user
from app.services.db_tester import DatabaseConfig, DatabaseTester
from app.services.security.audit_service import log_audit
from app.services.security.sql_validator import (
    SQLValidationError,
    add_limit,
    validate_sql,
)

router = APIRouter()


def _get_assertion_or_404(db: Session, assertion_id: str) -> DbAssertion:
    assertion = db.get(DbAssertion, assertion_id)
    if not assertion:
        raise NotFoundError("数据库断言", assertion_id)
    return assertion


def _bind_variables(sql_template: str, variables: dict) -> tuple[str, dict]:
    """将 SQL 模板中的 {{var}} 转换为参数绑定占位符 :var。

    SEC-07: 使用 SQLAlchemy 参数绑定代替字符串拼接，防止 SQL 注入。
    返回 (parameterized_sql, params_dict)。
    如果模板中的 {{var}} 在 variables 中不存在，抛出 ValidationError。
    """
    params: dict = {}
    missing: list[str] = []

    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        if key in variables:
            params[key] = variables[key]
            return f":{key}"
        missing.append(key)
        return str(match.group(0))

    parameterized = re.sub(r"\{\{\s*(\w+)\s*\}\}", _replacer, sql_template)
    if missing:
        raise ValidationError(f"SQL 模板中有未匹配的变量: {', '.join(missing)}")
    return parameterized, params


def _build_db_config(db_config: dict) -> DatabaseConfig:
    """从 Environment.db_config 构建 DatabaseConfig.

    Environment 存储的字段名为 ``user``，而 DatabaseConfig 使用 ``username``。
    """
    from app.services.security.secret_crypto import (
        SecretCryptoError,
        decrypt_db_config,
    )

    try:
        decrypted_config = decrypt_db_config(db_config) or {}
    except (SecretCryptoError, TypeError) as exc:
        raise ValidationError("数据库配置解密失败", detail=str(exc)) from exc

    kwargs: dict = {"db_type": decrypted_config.get("db_type", "sqlite")}
    for key in ("host", "port", "database", "driver"):
        if key in decrypted_config and decrypted_config[key] is not None:
            kwargs[key] = decrypted_config[key]
    # user -> username 映射
    username = decrypted_config.get("username") or decrypted_config.get("user")
    if username is not None:
        kwargs["username"] = username
    if "password" in decrypted_config and decrypted_config["password"] is not None:
        kwargs["password"] = decrypted_config["password"]
    return DatabaseConfig(**kwargs)


def _evaluate(rows: list[dict], expected_result: dict) -> tuple[bool, object]:
    """根据 expected_result 中的 operator 比对查询结果.

    Returns:
        (passed, actual)
    """
    operator = expected_result.get("operator", "equals")
    field = expected_result.get("field")
    expected_value = expected_result.get("value")

    if operator == "count":
        actual = len(rows)
        return actual == expected_value, actual

    if operator == "exists":
        if not rows:
            return False, None
        actual = field in rows[0]
        return actual, actual

    # 字段值比对类操作符
    if not rows:
        return False, None
    actual: Any = (list(rows[0].values())[0] if rows[0] else None) if field is None else rows[0].get(field)

    if operator == "equals":
        return actual == expected_value, actual
    if operator == "contains":
        try:
            return expected_value in actual, actual
        except TypeError:
            return str(expected_value) in str(actual), actual
    if operator == "greater_than":
        try:
            return actual > expected_value, actual
        except TypeError:
            return False, actual
    if operator == "less_than":
        try:
            return actual < expected_value, actual
        except TypeError:
            return False, actual

    raise ValidationError(f"不支持的操作符: {operator}")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=DataResponse[list[DbAssertionResponse]])
def list_db_assertions(test_case_id: str, db: Session = Depends(get_db)):
    """列出指定用例的数据库断言."""
    stmt = select(DbAssertion).where(DbAssertion.test_case_id == test_case_id).order_by(DbAssertion.created_at.asc())
    items = db.execute(stmt).scalars().all()
    return DataResponse[list[DbAssertionResponse]](data=items)


@router.post("", response_model=DataResponse[DbAssertionResponse])
def create_db_assertion(payload: DbAssertionCreate, db: Session = Depends(get_db)):
    """创建数据库断言."""
    assertion = DbAssertion(**payload.model_dump())
    db.add(assertion)
    db.commit()
    db.refresh(assertion)
    return DataResponse[DbAssertionResponse](data=assertion)


@router.put("/{assertion_id}", response_model=DataResponse[DbAssertionResponse])
def update_db_assertion(
    assertion_id: str,
    payload: DbAssertionUpdate,
    db: Session = Depends(get_db),
):
    """更新数据库断言."""
    assertion = _get_assertion_or_404(db, assertion_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assertion, field, value)
    db.commit()
    db.refresh(assertion)
    return DataResponse[DbAssertionResponse](data=assertion)


@router.delete("/{assertion_id}", response_model=ResponseBase)
def delete_db_assertion(assertion_id: str, db: Session = Depends(get_db)):
    """删除数据库断言."""
    assertion = _get_assertion_or_404(db, assertion_id)
    db.delete(assertion)
    db.commit()
    return ResponseBase()


@router.post("/{assertion_id}/test", response_model=DataResponse[dict])
def test_db_assertion(
    assertion_id: str,
    env_id: str,
    variables: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """测试单条数据库断言（执行 SQL 并比对结果）.

    SEC-07: SQL AST 校验 + 参数绑定 + 行数限额。
    SEC-09: 执行结果写入审计日志。
    """
    assertion = _get_assertion_or_404(db, assertion_id)

    # SEC-07: 变量参数绑定（{{var}} -> :var），防止 SQL 注入
    sql, params = _bind_variables(assertion.sql_template, variables or {})

    # SEC-07: SQL AST 校验（仅允许只读 SELECT）
    try:
        sql = validate_sql(sql)
    except SQLValidationError as e:
        log_audit(
            db,
            actor_id=current_user.id,
            actor_name=current_user.username,
            action="execute",
            resource_type="db_assertion",
            resource_id=assertion_id,
            before={"sql_template": assertion.sql_template},
            after={"sql": sql},
            result="failed",
            error_message=str(e),
        )
        raise ValidationError(str(e)) from e

    # SEC-07: 添加行数限额（默认 1000 行）
    sql = add_limit(sql, 1000)

    # 获取环境配置
    env = db.get(Environment, env_id)
    if not env:
        raise NotFoundError("环境", env_id)
    if not env.db_config:
        raise ValidationError(f"环境 '{env_id}' 未配置 db_config")

    # 构建数据库配置并执行查询（参数绑定）
    db_config = _build_db_config(env.db_config)
    tester = DatabaseTester()
    rows = tester.execute_query(db_config, sql, params)

    # 比对结果
    expected_result = assertion.expected_result or {}
    passed, actual = _evaluate(rows, expected_result)

    # SEC-09: 审计日志
    log_audit(
        db,
        actor_id=current_user.id,
        actor_name=current_user.username,
        action="execute",
        resource_type="db_assertion",
        resource_id=assertion_id,
        after={"sql": sql, "passed": passed, "actual": actual},
        result="success",
    )

    return DataResponse[dict](
        data={
            "passed": passed,
            "sql": sql,
            "actual": actual,
            "expected": expected_result,
        }
    )
