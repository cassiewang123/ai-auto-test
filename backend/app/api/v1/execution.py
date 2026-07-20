"""测试执行 API：直接执行接口测试并返回结果.

端点：
    POST /api/v1/execution/run         — 直接执行（支持文件上传 + 前置条件）
    POST /api/v1/execution/run/{case_id} — 执行已保存的用例
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from test_engine.executor import TestCaseExecutor
from test_engine.request_builder import RequestBuilder
from test_engine.variable_extractor import VariableExtractor

from app.config import get_settings
from app.core.exceptions import AppException, NotFoundError
from app.database import get_db
from app.models.user import User
from app.runners.script_process import run_script_in_subprocess
from app.schemas.common import DataResponse
from app.schemas.execution import (
    ExecuteRequest,
    ExecutionResult,
    PreRequest,
    RequestDefinition,
)
from app.services.auth_service import get_current_user
from app.services.project_access import ensure_project_role
from app.services.security.data_redaction import redact_sensitive_data
from app.services.security.url_policy import URLPolicy

router = APIRouter()


def _build_url_policy() -> URLPolicy:
    """从应用配置构建 URLPolicy 实例（SSRF 防护）."""
    settings = get_settings()
    allowed = [d.strip() for d in settings.URL_ALLOWED_DOMAINS.split(",") if d.strip()]
    blocked = [d.strip() for d in settings.URL_BLOCKED_DOMAINS.split(",") if d.strip()]
    return URLPolicy(
        allow_private=settings.URL_ALLOW_PRIVATE,
        allowed_domains=allowed,
        blocked_domains=blocked,
    )


_settings = get_settings()
_url_policy = _build_url_policy()
_max_response_size = _settings.URL_MAX_RESPONSE_SIZE

_executor = TestCaseExecutor(
    request_builder=RequestBuilder(
        url_policy=_url_policy,
        max_response_size=_max_response_size,
    )
)


# ---------- 辅助函数 ----------


def _build_request_def(req: ExecuteRequest) -> RequestDefinition:
    """从 API 入参构建 RequestDefinition."""
    return RequestDefinition(
        method=req.method,
        url=req.url,
        headers=req.headers,
        params=req.params,
        body=req.body,
        graphql_query=req.graphql_query,
        files=req.files if req.files else None,
        extract_rules=req.extract_rules,
        timeout=req.timeout,
    )


def _serialize_result(result: ExecutionResult) -> dict:
    """将 ExecutionResult 序列化为可 JSON 响应的字典."""
    return redact_sensitive_data(
        {
            "test_case_id": result.test_case_id,
            "status": result.status,
            "duration": round(result.duration, 4),
            "request": result.request.model_dump() if result.request else None,
            "response": {
                "status_code": result.response.status_code,
                "headers": result.response.headers,
                "body": result.response.body,
                "elapsed": round(result.response.elapsed, 4),
                "text": result.response.text[:5000] if result.response.text else "",
            }
            if result.response
            else None,
            "assertion_results": [r.model_dump() for r in result.assertion_results],
            "extracted_variables": [v.model_dump() for v in result.extracted_variables],
            "error_message": result.error_message,
            "executed_at": result.executed_at.isoformat(),
        }
    )


def _run_pre_requests(
    pre_requests: list[PreRequest],
    variables: dict[str, Any],
) -> tuple[dict[str, Any], list[dict]]:
    """执行前置请求链，提取变量合并到变量池.

    返回：(合并后的变量池, 前置请求结果列表)
    """
    pool = dict(variables)
    extractor = VariableExtractor()
    builder = RequestBuilder(
        url_policy=_url_policy,
        max_response_size=_max_response_size,
    )
    pre_results: list[dict] = []

    for i, pre in enumerate(pre_requests):
        try:
            req_def = RequestDefinition(
                method=pre.method,
                url=pre.url,
                headers=pre.headers,
                params=pre.params,
                body=pre.body,
                extract_rules=pre.extract_rules,
                timeout=30.0,
            )
            response = builder.send(req_def, pool)

            # 提取变量并合并到池
            extracted = extractor.extract(response, pre.extract_rules)
            pool.update(extracted)

            pre_results.append(
                {
                    "index": i,
                    "name": pre.name or f"前置请求 {i + 1}",
                    "status_code": response.status_code,
                    "elapsed": round(response.elapsed, 4),
                    "extracted_variables": {k: str(v)[:200] for k, v in extracted.items()},
                    "success": True,
                }
            )
        except Exception as exc:
            pre_results.append(
                {
                    "index": i,
                    "name": pre.name or f"前置请求 {i + 1}",
                    "status_code": None,
                    "elapsed": 0,
                    "extracted_variables": {},
                    "success": False,
                    "error": str(exc),
                }
            )

    return pool, pre_results


def _run_script(script: str, context: dict) -> dict:
    """Execute a pre/post script outside the API process."""
    return run_script_in_subprocess(
        script,
        context,
        timeout_seconds=get_settings().SCRIPT_EXECUTION_TIMEOUT,
    )


def _ensure_sync_execution_allowed() -> None:
    """Reject synchronous execution when disabled or running in production."""
    settings = get_settings()
    environment = str(getattr(settings, "ENVIRONMENT", "development"))
    is_production = environment.strip().lower() in {"production", "prod"}
    if is_production or not settings.ALLOW_SYNC_EXECUTION:
        raise AppException(
            status_code=403,
            message="生产环境不允许同步执行测试，请使用异步任务 API /api/v1/jobs",
        )


# ---------- 失败重试 ----------


def _execute_with_retry(
    executor: TestCaseExecutor,
    request_def: RequestDefinition,
    assertions: list[dict],
    variables: dict[str, Any],
    retry_count: int,
    retry_interval: float,
    test_case_id: str = "",
) -> tuple[Any, list[dict]]:
    """执行测试，失败时按 retry_count 自动重试.

    返回：(最终执行结果, 每次尝试的摘要列表)
    """
    attempts: list[dict] = []
    result = None
    total_attempts = max(retry_count + 1, 1)
    for attempt in range(total_attempts):
        result = executor.execute(
            request_def=request_def,
            assertions=assertions,
            variables=variables,
            test_case_id=test_case_id,
        )
        attempts.append(
            {
                "attempt": attempt + 1,
                "status": result.status,
                "duration": round(result.duration, 4),
                "status_code": result.response.status_code if result.response else None,
                "error": result.error_message,
            }
        )
        # 通过则不再重试
        if result.status == "passed":
            break
        # 未通过且还有重试机会，则等待后重试
        if attempt < total_attempts - 1 and retry_interval > 0:
            time.sleep(retry_interval)
    return result, attempts


# ---------- Cookie / 会话管理 ----------


def _build_cookie_header(cookies: list[dict], existing_headers: dict) -> dict:
    """将 cookies 列表合并到请求 headers 的 Cookie 字段."""
    if not cookies:
        return existing_headers
    headers = dict(existing_headers or {})
    parts = []
    for c in cookies:
        name = c.get("name")
        value = c.get("value", "")
        if name:
            parts.append(f"{name}={value}")
    if parts:
        existing = headers.get("Cookie") or headers.get("cookie") or ""
        merged = "; ".join(filter(None, [existing, "; ".join(parts)]))
        headers["Cookie"] = merged
        headers.pop("cookie", None)
    return headers


def _extract_cookies(response_headers: dict) -> list[dict]:
    """从响应头解析 Set-Cookie，返回 cookie 列表."""
    cookies: list[dict] = []
    if not response_headers:
        return cookies
    # httpx 将多个 Set-Cookie 合并为列表或逗号分隔字符串
    raw = response_headers.get("set-cookie")
    if not raw:
        return cookies
    if isinstance(raw, str):
        items = [s.strip() for s in raw.split(",") if s.strip()]
    elif isinstance(raw, list):
        items = raw
    else:
        items = [str(raw)]
    for item in items:
        # 每个 Set-Cookie 形如 "name=value; Path=/; HttpOnly"
        first = item.split(";")[0].strip()
        if "=" not in first:
            continue
        name, _, value = first.partition("=")
        cookie = {"name": name.strip(), "value": value.strip()}
        # 解析 Path / Domain
        for attr in item.split(";")[1:]:
            attr = attr.strip()
            if "=" in attr:
                k, _, v = attr.partition("=")
                k = k.strip().lower()
                if k in ("path", "domain"):
                    cookie[k] = v.strip()
            elif attr.lower() in ("httponly", "secure"):
                cookie[attr.lower()] = True
        cookies.append(cookie)
    return cookies


def _merge_cookies(existing: list[dict], new: list[dict]) -> list[dict]:
    """合并 cookie 列表，同 name 覆盖."""
    merged = {c.get("name"): c for c in (existing or [])}
    for c in new or []:
        merged[c.get("name")] = c
    return list(merged.values())


# ---------- 全局变量 ----------


def _load_global_variables(db: Session, project_id: str | None = None) -> dict[str, Any]:
    """从数据库加载全局变量并按类型转换，返回变量字典."""
    from app.models import GlobalVariable

    query = db.query(GlobalVariable)
    if project_id:
        # 全局变量 + 该项目的工作空间变量
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
        variables[var.name] = _cast_variable(var.value, var.var_type)
    return variables


def _cast_variable(value: str | None, var_type: str) -> Any:
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


def _resolve_environment_url(url: str, base_url: str | None) -> str:
    """Resolve relative direct-execution URLs against the selected environment."""
    if not base_url or url.lower().startswith(("http://", "https://")):
        return url
    return f"{base_url.rstrip('/')}/{url.lstrip('/')}"


def _load_direct_execution_context(
    db: Session,
    current_user: User,
    *,
    project_id: str | None,
    environment_id: str | None,
    request_variables: dict[str, Any],
    request_cookies: list[dict],
) -> tuple[dict[str, Any], list[dict], str | None]:
    """Load project variables and the selected environment for a quick test."""
    if project_id:
        ensure_project_role(db, current_user, project_id, "tester")

    variables = _load_global_variables(db, project_id)
    cookies: list[dict] = []
    base_url: str | None = None

    if environment_id:
        from app.models.environment import Environment
        from app.services.security.secret_crypto import (
            SecretCryptoError,
            decrypt_cookies,
        )

        environment = db.get(Environment, environment_id)
        if environment is None:
            raise NotFoundError("Environment", environment_id)
        variables.update(environment.variables or {})
        base_url = environment.base_url
        try:
            cookies = decrypt_cookies(environment.cookies)
        except (SecretCryptoError, TypeError) as exc:
            raise AppException(
                status_code=422,
                message="环境 Cookie 解密失败",
                detail=str(exc),
            ) from exc

    variables.update(request_variables)
    cookies = _merge_cookies(cookies, request_cookies)
    return variables, cookies, base_url


def _resolve_pre_request_urls(
    pre_requests: list[PreRequest],
    base_url: str | None,
) -> list[PreRequest]:
    if not base_url:
        return pre_requests
    return [
        request.model_copy(
            update={"url": _resolve_environment_url(request.url, base_url)}
        )
        for request in pre_requests
    ]


# ---------- API 端点 ----------


@router.post("/run", response_model=DataResponse[dict])
def run_test(
    req: ExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """直接执行请求定义，支持文件上传与前置条件.

    流程：
        1. 执行前置请求链，提取变量合并到变量池
        2. 执行前置脚本（可修改变量）
        3. 合并 Cookie 到请求头，用变量池执行主请求（失败按 retry_count 重试）
        4. 执行后置脚本（可访问响应）
        5. 保存历史调用记录
    """
    _ensure_sync_execution_allowed()

    from app.api.v1.history import save_history

    context_variables, request_cookies, base_url = (
        _load_direct_execution_context(
            db,
            current_user,
            project_id=req.project_id,
            environment_id=req.environment_id,
            request_variables=req.variables,
            request_cookies=req.cookies,
        )
    )
    resolved_url = _resolve_environment_url(req.url, base_url)
    resolved_pre_requests = _resolve_pre_request_urls(req.pre_requests, base_url)

    # 1. 前置条件
    merged_vars, pre_results = _run_pre_requests(
        resolved_pre_requests,
        context_variables,
    )

    # 2. 前置脚本
    pre_script_result = None
    if req.pre_script:
        ctx = {
            "variables": merged_vars,
            "request": req.model_copy(
                update={"url": resolved_url}
            ).model_dump(),
        }
        pre_script_result = _run_script(req.pre_script, ctx)
        # 脚本可能修改了 variables
        if pre_script_result.get("success") and pre_script_result.get("variables"):
            merged_vars = pre_script_result["variables"]

    # 3. 合并 Cookie 并执行主请求（含重试）
    request_def = _build_request_def(
        req.model_copy(update={"url": resolved_url})
    )
    request_def.headers = _build_cookie_header(
        request_cookies,
        request_def.headers,
    )
    result, attempts = _execute_with_retry(
        executor=_executor,
        request_def=request_def,
        assertions=req.assertions,
        variables=merged_vars,
        retry_count=req.retry_count,
        retry_interval=req.retry_interval,
    )

    # 4. 后置脚本
    post_script_result = None
    if req.post_script:
        resp_data = None
        if result.response:
            resp_data = {
                "status_code": result.response.status_code,
                "headers": result.response.headers,
                "body": result.response.body,
                "text": result.response.text,
                "elapsed": result.response.elapsed,
            }
        ctx = {"variables": merged_vars, "response": resp_data}
        post_script_result = _run_script(req.post_script, ctx)

    serialized = _serialize_result(result)
    serialized["pre_request_results"] = pre_results
    serialized["pre_script_result"] = pre_script_result
    serialized["post_script_result"] = post_script_result
    serialized["retry_attempts"] = attempts

    # 捕获并返回会话 Cookie
    session_cookies = []
    if result.response and result.response.headers:
        new_cookies = _extract_cookies(result.response.headers)
        session_cookies = _merge_cookies(request_cookies, new_cookies)
    serialized["session_cookies"] = redact_sensitive_data(
        session_cookies,
        parent_key="session_cookies",
    )
    serialized = redact_sensitive_data(serialized)

    # 5. 保存历史记录
    save_history(
        db,
        method=req.method,
        url=resolved_url,
        status=result.status,
        duration=result.duration,
        headers=request_def.headers,
        params=req.params,
        body=req.body,
        status_code=result.response.status_code if result.response else None,
        response_headers=result.response.headers if result.response else None,
        response_body=result.response.body if result.response else None,
        response_text=result.response.text if result.response else None,
        assertion_results=[r.model_dump() for r in result.assertion_results],
        error_message=result.error_message,
        pre_request_results=pre_results,
        has_files=bool(req.files),
        source="quick_test",
        project_id=req.project_id,
        created_by=current_user.id,
    )

    return DataResponse(data=serialized)


@router.post("/run-multipart", response_model=DataResponse[dict])
async def run_test_multipart(
    method: str = Form(...),
    url: str = Form(...),
    headers: str = Form("{}"),
    params: str = Form("{}"),
    body: str = Form(""),
    extract_rules: str = Form("[]"),
    assertions: str = Form("[]"),
    variables: str = Form("{}"),
    timeout: float = Form(30.0),
    pre_requests: str = Form("[]"),
    cookies: str = Form("[]"),
    pre_script: str = Form(""),
    post_script: str = Form(""),
    retry_count: int = Form(0),
    retry_interval: float = Form(1.0),
    project_id: str | None = Form(None),
    environment_id: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """通过 multipart/form-data 执行请求，支持原生文件上传.

    headers/params/body/assertions/variables/pre_requests/cookies 均为 JSON 字符串。
    files 为上传的文件列表，每个文件需附带 field 名（通过 filename 前缀传递）。
    """
    _ensure_sync_execution_allowed()

    from app.api.v1.history import save_history

    parsed_headers = json.loads(headers) if headers else {}
    parsed_params = json.loads(params) if params else {}
    parsed_body = json.loads(body) if body else None
    parsed_extract_rules = json.loads(extract_rules) if extract_rules else []
    parsed_assertions = json.loads(assertions) if assertions else []
    parsed_variables = json.loads(variables) if variables else {}
    parsed_pre = [PreRequest(**p) for p in json.loads(pre_requests)] if pre_requests else []
    parsed_cookies = json.loads(cookies) if cookies else []

    context_variables, request_cookies, base_url = (
        _load_direct_execution_context(
            db,
            current_user,
            project_id=project_id,
            environment_id=environment_id,
            request_variables=parsed_variables,
            request_cookies=parsed_cookies,
        )
    )
    resolved_url = _resolve_environment_url(url, base_url)
    parsed_pre = _resolve_pre_request_urls(parsed_pre, base_url)

    # 转换上传文件为 RequestBuilder 格式
    file_list = []
    for f in files:
        content = await f.read()
        file_list.append(
            {
                "field": f.filename.split("::")[0] if "::" in (f.filename or "") else "file",
                "filename": f.filename.split("::")[1] if "::" in (f.filename or "") else (f.filename or "upload"),
                "content": content,
                "content_type": f.content_type or "application/octet-stream",
            }
        )

    # 前置条件
    merged_vars, pre_results = _run_pre_requests(parsed_pre, context_variables)

    # 前置脚本
    pre_script_result = None
    if pre_script and pre_script.strip():
        ctx = {
            "variables": merged_vars,
            "request": {
                "method": method,
                "url": resolved_url,
                "headers": parsed_headers,
                "params": parsed_params,
                "body": parsed_body,
            },
        }
        pre_script_result = _run_script(pre_script, ctx)
        if pre_script_result.get("success") and pre_script_result.get("variables"):
            merged_vars = pre_script_result["variables"]

    # 主请求（合并 Cookie + 重试）
    parsed_headers = _build_cookie_header(request_cookies, parsed_headers)
    request_def = RequestDefinition(
        method=method,
        url=resolved_url,
        headers=parsed_headers,
        params=parsed_params,
        body=parsed_body,
        files=file_list if file_list else None,
        extract_rules=parsed_extract_rules,
        timeout=timeout,
    )
    result, attempts = _execute_with_retry(
        executor=_executor,
        request_def=request_def,
        assertions=parsed_assertions,
        variables=merged_vars,
        retry_count=retry_count,
        retry_interval=retry_interval,
    )

    # 后置脚本
    post_script_result = None
    if post_script and post_script.strip():
        resp_data = None
        if result.response:
            resp_data = {
                "status_code": result.response.status_code,
                "headers": result.response.headers,
                "body": result.response.body,
                "text": result.response.text,
                "elapsed": result.response.elapsed,
            }
        ctx = {"variables": merged_vars, "response": resp_data}
        post_script_result = _run_script(post_script, ctx)

    serialized = _serialize_result(result)
    serialized["pre_request_results"] = pre_results
    serialized["pre_script_result"] = pre_script_result
    serialized["post_script_result"] = post_script_result
    serialized["retry_attempts"] = attempts

    # 捕获并返回会话 Cookie
    session_cookies = []
    if result.response and result.response.headers:
        new_cookies = _extract_cookies(result.response.headers)
        session_cookies = _merge_cookies(request_cookies, new_cookies)
    serialized["session_cookies"] = redact_sensitive_data(
        session_cookies,
        parent_key="session_cookies",
    )
    serialized = redact_sensitive_data(serialized)

    # 保存历史记录
    save_history(
        db,
        method=method,
        url=resolved_url,
        status=result.status,
        duration=result.duration,
        headers=parsed_headers,
        params=parsed_params,
        body=parsed_body,
        status_code=result.response.status_code if result.response else None,
        response_headers=result.response.headers if result.response else None,
        response_body=result.response.body if result.response else None,
        response_text=result.response.text if result.response else None,
        assertion_results=[r.model_dump() for r in result.assertion_results],
        error_message=result.error_message,
        pre_request_results=pre_results,
        has_files=bool(file_list),
        source="quick_test",
        project_id=project_id,
        created_by=current_user.id,
    )

    return DataResponse(data=serialized)


@router.post("/run/{case_id}", response_model=DataResponse[dict])
def run_saved_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行已保存的用例：从数据库读取定义后执行.

    变量合并优先级：临时（运行参数）> 环境变量 > 全局变量。
    同时支持用例上配置的前置/后置脚本、失败重试与 Cookie 会话。
    """
    _ensure_sync_execution_allowed()

    from app.models.test_case import TestCase

    case = db.query(TestCase).filter(TestCase.id == case_id).first()
    if not case:
        raise NotFoundError("TestCase", case_id)

    # 1. 加载全局变量（优先级最低）
    variables: dict[str, Any] = _load_global_variables(db, case.project_id)

    env_cookies: list[dict] = []
    if case.environment_id:
        from app.models.environment import Environment

        env = db.query(Environment).filter(Environment.id == case.environment_id).first()
        if env:
            from app.services.security.secret_crypto import (
                SecretCryptoError,
                decrypt_cookies,
            )

            # 环境变量覆盖全局变量（优先级：环境 > 全局）
            variables.update(env.variables or {})
            try:
                env_cookies = decrypt_cookies(env.cookies)
            except (SecretCryptoError, TypeError) as exc:
                raise AppException(
                    status_code=422,
                    message="环境 Cookie 解密失败",
                    detail=str(exc),
                ) from exc
            if not case.url.startswith("http"):
                case_url = f"{env.base_url.rstrip('/')}/{case.url.lstrip('/')}"
            else:
                case_url = case.url
        else:
            case_url = case.url
    else:
        case_url = case.url

    # 2. 前置脚本（可修改变量）
    pre_script_result = None
    if case.pre_script:
        ctx = {
            "variables": variables,
            "request": {
                "method": case.method,
                "url": case_url,
                "headers": case.headers,
                "params": case.params,
                "body": case.body,
            },
        }
        pre_script_result = _run_script(case.pre_script, ctx)
        if pre_script_result.get("success") and pre_script_result.get("variables"):
            variables = pre_script_result["variables"]

    # 3. 合并 Cookie 并构建请求
    request_headers = _build_cookie_header(env_cookies, case.headers or {})
    request_def = RequestDefinition(
        method=case.method,
        url=case_url,
        headers=request_headers,
        params=case.params or {},
        body=case.body,
        graphql_query=case.graphql_query,
        extract_rules=case.extract_rules or [],
        timeout=30.0,
    )

    assertions = []
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

    # 4. 执行（含失败重试）
    result, attempts = _execute_with_retry(
        executor=_executor,
        request_def=request_def,
        assertions=assertions,
        variables=variables,
        retry_count=case.retry_count or 0,
        retry_interval=case.retry_interval or 1.0,
        test_case_id=case_id,
    )

    # 5. 后置脚本
    post_script_result = None
    if case.post_script:
        resp_data = None
        if result.response:
            resp_data = {
                "status_code": result.response.status_code,
                "headers": result.response.headers,
                "body": result.response.body,
                "text": result.response.text,
                "elapsed": result.response.elapsed,
            }
        ctx = {"variables": variables, "response": resp_data}
        post_script_result = _run_script(case.post_script, ctx)

    serialized = _serialize_result(result)
    serialized["pre_script_result"] = pre_script_result
    serialized["post_script_result"] = post_script_result
    serialized["retry_attempts"] = attempts

    # 捕获并返回会话 Cookie
    session_cookies = []
    if result.response and result.response.headers:
        new_cookies = _extract_cookies(result.response.headers)
        session_cookies = _merge_cookies(env_cookies, new_cookies)
    serialized["session_cookies"] = redact_sensitive_data(
        session_cookies,
        parent_key="session_cookies",
    )
    serialized = redact_sensitive_data(serialized)

    from app.api.v1.history import save_history
    from app.models.test_result import TestResult
    from app.models.test_run_summary import TestRunSummary

    run_id = str(uuid.uuid4())
    db_result = TestResult(
        run_id=run_id,
        test_case_id=case_id,
        status=result.status,
        duration=result.duration,
        request_snapshot=redact_sensitive_data(request_def.model_dump()),
        response_snapshot=serialized.get("response"),
        assertion_results=[r.model_dump() for r in result.assertion_results],
        error_message=result.error_message,
    )
    summary = TestRunSummary(
        run_id=run_id,
        source="manual",
        project_id=case.project_id,
        created_by=current_user.id,
        total=1,
        passed=1 if result.status == "passed" else 0,
        failed=1 if result.status == "failed" else 0,
        error=1 if result.status not in {"passed", "failed", "skipped"} else 0,
        skipped=1 if result.status == "skipped" else 0,
        duration=result.duration,
    )
    db.add_all([db_result, summary])
    db.commit()

    save_history(
        db,
        method=case.method,
        url=case_url,
        status=result.status,
        duration=result.duration,
        headers=request_headers,
        params=case.params,
        body=case.body,
        status_code=result.response.status_code if result.response else None,
        response_headers=result.response.headers if result.response else None,
        response_body=result.response.body if result.response else None,
        response_text=result.response.text if result.response else None,
        assertion_results=[r.model_dump() for r in result.assertion_results],
        error_message=result.error_message,
        source="saved_case",
        test_case_id=case.id,
        project_id=case.project_id,
        created_by=current_user.id,
    )
    serialized["run_id"] = run_id
    return DataResponse(data=serialized)
