"""CI/CD 集成服务层：API Token 管理、触发执行、Webhook 回调."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session
from test_engine.executor import TestCaseExecutor

from app.core.exceptions import AuthenticationError, NotFoundError
from app.services.security.secret_crypto import (
    SecretCryptoError,
    decrypt_cookies,
    decrypt_secret,
    decrypt_url,
    mask_url,
    redact_url_from_text,
)

# 模块级执行器单例，便于测试 mock（patch app.services.ci_cd_service._ci_executor）
_ci_executor = TestCaseExecutor()

TOKEN_PREFIX = "air_"
# token 前缀展示长度（含 "air_" 前缀）
TOKEN_PREFIX_LEN = 8


# ---------------------------------------------------------------------------
# API Token
# ---------------------------------------------------------------------------

def _hash_token(token: str) -> str:
    """使用 HMAC-SHA256 对 token 做哈希，密钥为应用 SECRET_KEY."""
    from app.config import get_settings

    secret_key = get_settings().SECRET_KEY
    return hmac.new(
        secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def mask_token(token: str) -> str:
    """对 token 脱敏：保留前缀与前 8 位、末 4 位，中间以 ... 替代."""
    if not token:
        return ""
    if len(token) <= 16:
        return token[: len(TOKEN_PREFIX) + 2] + "***"
    return f"{token[: len(TOKEN_PREFIX) + 6]}...{token[-4:]}"


def create_token(
    db: Session,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
    user_id: str | None = None,
):
    """生成并保存 API Token.

    SEC-03 改造：明文 token 经 HMAC-SHA256 哈希后存储到 token_hash，
    同时存储前 8 位前缀到 token_prefix 用于展示。
    返回 (ApiToken 记录, 明文 token)。明文 token 仅在创建时返回一次。
    """
    from app.models.api_token import ApiToken

    plaintext = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    token_hash = _hash_token(plaintext)
    token_prefix = plaintext[:TOKEN_PREFIX_LEN]
    record = ApiToken(
        name=name,
        token_hash=token_hash,
        token_prefix=token_prefix,
        scopes=list(scopes),
        expires_at=expires_at,
        user_id=user_id,
        is_active=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, plaintext


def validate_token(
    db: Session,
    token: str,
    required_scope: str | None = None,
):
    """验证 token 有效性、活跃状态、过期时间，可选检查 scope。

    SEC-03 改造：将传入的明文 token 做 HMAC-SHA256 哈希后与数据库
    token_hash 比对。
    验证通过时更新 last_used_at。失败抛出 AuthenticationError。
    """
    from app.models.api_token import ApiToken

    token_hash = _hash_token(token)
    record = (
        db.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()
    )
    if not record:
        raise AuthenticationError("无效的 API Token")
    if not record.is_active:
        raise AuthenticationError("API Token 已被吊销")
    if record.expires_at is not None and record.expires_at < datetime.now():
        raise AuthenticationError("API Token 已过期")
    if required_scope is not None and required_scope not in (record.scopes or []):
        raise AuthenticationError(f"缺少权限: {required_scope}")
    record.last_used_at = datetime.now()
    db.commit()
    db.refresh(record)
    return record


def revoke_token(db: Session, token_id: str) -> None:
    """吊销（删除）API Token."""
    from app.models.api_token import ApiToken

    record = db.get(ApiToken, token_id)
    if not record:
        raise NotFoundError("API Token", token_id)
    db.delete(record)
    db.commit()


# ---------------------------------------------------------------------------
# 触发执行
# ---------------------------------------------------------------------------

def _build_cookie_headers(
    headers: dict[str, Any],
    cookies: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge decrypted environment Cookies into request headers."""
    merged = dict(headers)
    pairs = [
        f"{cookie.get('name')}={cookie.get('value')}"
        for cookie in cookies
        if cookie.get("name") and cookie.get("value") is not None
    ]
    if not pairs:
        return merged
    existing = merged.get("Cookie") or merged.get("cookie")
    cookie_header = "; ".join(pairs)
    merged["Cookie"] = (
        f"{existing}; {cookie_header}" if existing else cookie_header
    )
    merged.pop("cookie", None)
    return merged


def _build_request_def(
    case,
    variables: dict[str, Any],
    base_url: str | None = None,
    cookies: list[dict[str, Any]] | None = None,
):
    """从 TestCase 模型构建 RequestDefinition，必要时拼接环境 base_url."""
    from app.schemas.execution import RequestDefinition

    url = case.url
    if base_url and not url.startswith("http"):
        url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"

    return RequestDefinition(
        method=case.method,
        url=url,
        headers=_build_cookie_headers(
            dict(case.headers or {}),
            cookies or [],
        ),
        params=dict(case.params or {}),
        body=case.body,
        graphql_query=case.graphql_query,
        files=list(case.files) if case.files else None,
        extract_rules=list(case.extract_rules or []),
        timeout=30.0,
    )


def _build_assertions(case) -> list[dict]:
    """从 TestCase 关联的断言规则构建断言列表."""
    assertions: list[dict] = []
    for a in sorted(case.assertions, key=lambda x: x.order):
        assertions.append(
            {
                "assertion_type": a.assertion_type,
                "expression": a.expression,
                "operator": a.operator,
                "expected": a.expected,
                "priority": a.priority,
                "order": a.order,
            }
        )
    return assertions


def trigger_execution(
    db: Session,
    plan_id: str | None = None,
    case_ids: list[str] | None = None,
    environment_id: str | None = None,
    source: str = "ci",
) -> dict:
    """触发执行：通过 plan_id 或 case_ids 解析用例并执行。

    流程：
        1. 解析目标用例列表（plan_id 取计划项，case_ids 取指定用例）
        2. 加载环境变量与 base_url
        3. 逐个执行用例，统计 passed/failed/error
        4. 创建 TestRunSummary 汇总记录（source 标记来源）
        5. 返回 run_id、状态与统计
    """
    from app.models import TestCase, TestPlan, TestRunSummary
    from app.models.environment import Environment

    # 1. 解析用例
    cases: list[TestCase] = []
    if plan_id:
        plan = db.get(TestPlan, plan_id)
        if not plan:
            raise NotFoundError("测试计划", plan_id)
        items = sorted(plan.items, key=lambda i: i.order)
        for item in items:
            if item.test_case is not None:
                cases.append(item.test_case)
    elif case_ids:
        for cid in case_ids:
            case = db.get(TestCase, cid)
            if case is not None:
                cases.append(case)

    # 2. 环境变量
    variables: dict[str, Any] = {}
    base_url: str | None = None
    environment_cookies: list[dict[str, Any]] = []
    if environment_id:
        env = db.get(Environment, environment_id)
        if env:
            variables = dict(env.variables or {})
            base_url = env.base_url
            try:
                environment_cookies = decrypt_cookies(env.cookies)
            except (SecretCryptoError, TypeError) as exc:
                raise ValueError("环境 Cookie 解密失败") from exc

    # 3. 执行
    run_id = str(uuid.uuid4())
    results: list[dict] = []
    passed = 0
    failed = 0
    errored = 0
    total_duration = 0.0

    for case in cases:
        try:
            request_def = _build_request_def(
                case,
                variables,
                base_url,
                environment_cookies,
            )
            assertions = _build_assertions(case)
            result = _ci_executor.execute(
                request_def=request_def,
                assertions=assertions,
                variables=variables,
                test_case_id=case.id,
            )
            status = result.status
            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
            else:
                errored += 1
            total_duration += result.duration
            results.append(
                {
                    "test_case_id": case.id,
                    "title": case.title,
                    "status": status,
                    "duration": round(result.duration, 4),
                    "status_code": result.response.status_code if result.response else None,
                    "error": result.error_message,
                }
            )
        except Exception as exc:  # noqa: BLE001 - 记录执行异常
            errored += 1
            results.append(
                {
                    "test_case_id": case.id,
                    "title": case.title,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    # 4. 汇总记录
    summary = TestRunSummary(
        run_id=run_id,
        source=source,
        total=len(cases),
        passed=passed,
        failed=failed,
        error=errored,
        skipped=0,
        duration=round(total_duration, 4),
        summary={"results": results},
    )
    db.add(summary)
    db.commit()

    # 5. 返回
    status = "passed" if failed == 0 and errored == 0 else "failed"
    message = f"执行完成: {passed} 通过, {failed} 失败, {errored} 错误"
    return {
        "run_id": run_id,
        "status": status,
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "error": errored,
        "message": message,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

def sign_payload(secret: str, payload: str | bytes) -> str:
    """计算 HMAC-SHA256 签名（十六进制）。payload 可为 str 或 bytes."""
    plaintext_secret = decrypt_secret(secret)
    if plaintext_secret is None:
        plaintext_secret = ""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hmac.new(
        plaintext_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def send_webhook(
    db: Session,
    event: str,
    payload: Any,
    only_webhook_id: str | None = None,
) -> list[dict]:
    """向匹配事件且启用的 Webhook 发送回调。

    每次发送携带：
        - Content-Type: application/json
        - X-Airetest-Signature: HMAC-SHA256(secret, body)
        - X-Airetest-Event: 事件名

    当指定 only_webhook_id 时，仅向该 Webhook 发送（忽略事件订阅与启用状态，
    用于测试回调）。返回每个 Webhook 的发送结果列表，单个异常不会中断其他。
    """
    from app.models.webhook_config import WebhookConfig

    if only_webhook_id is not None:
        target = db.get(WebhookConfig, only_webhook_id)
        configs = [target] if target is not None else []
    else:
        configs = (
            db.query(WebhookConfig).filter(WebhookConfig.is_active.is_(True)).all()
        )
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    results: list[dict] = []

    for cfg in configs:
        # 仅在广播模式下按事件订阅过滤
        if only_webhook_id is None and event not in (cfg.events or []):
            continue
        try:
            runtime_url = decrypt_url(cfg.url)
            if not runtime_url:
                raise ValueError("Webhook URL 未配置")
            signature = sign_payload(cfg.secret or "", body)
            headers = {
                "Content-Type": "application/json",
                "X-Airetest-Signature": signature,
                "X-Airetest-Event": event,
            }
            resp = httpx.post(
                runtime_url,
                content=body,
                headers=headers,
                timeout=10.0,
            )
            results.append(
                {
                    "webhook_id": cfg.id,
                    "url": mask_url(cfg.url),
                    "has_url": bool(cfg.url),
                    "status_code": resp.status_code,
                    "success": resp.is_success,
                }
            )
        except Exception as exc:  # noqa: BLE001 - 单个失败不影响其他
            results.append(
                {
                    "webhook_id": cfg.id,
                    "url": mask_url(cfg.url),
                    "has_url": bool(cfg.url),
                    "status_code": None,
                    "success": False,
                    "error": redact_url_from_text(str(exc), cfg.url),
                }
            )
    return results
