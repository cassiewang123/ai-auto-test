"""请求构建器：接收 RequestDefinition，用 httpx 发送真实 HTTP 请求，返回 ResponseData.

能力：
    - GET/POST/PUT/PATCH/DELETE 全方法
    - JSON body / form data / 文件上传（multipart）
    - GraphQL 请求（POST，body 含 query 与 variables）
    - {{variable}} 模板变量渲染（url / headers / params / body）
    - 记录请求耗时 elapsed
    - 超时控制（超时/网络异常向上抛出，由编排器捕获）
    - SEC-05: URLPolicy 出站策略校验（SSRF 防护）
    - FIX-03: follow_redirects=False + 手动重定向（每次重新校验 URL）
    - FIX-03: max_response_size 响应体大小限制

构造时可注入 transport（如 httpx.MockTransport）以便单元测试。
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.core.exceptions import ValidationError
from app.schemas.execution import RequestDefinition, ResponseData
from app.services.security.url_policy import URLPolicy

# 匹配 {{ var }} 形式的占位符
_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class RequestBuilder:
    """基于 httpx 的请求构建与发送."""

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        url_policy: URLPolicy | None = None,
        max_response_size: int = 10 * 1024 * 1024,
        max_redirects: int = 10,
    ) -> None:
        self._transport = transport
        self._url_policy = url_policy
        self._max_response_size = max_response_size
        self._max_redirects = max_redirects

    # ---------------- 公共 API ----------------
    def send(self, request_def: RequestDefinition, variables: dict | None = None) -> ResponseData:
        """渲染变量并发送请求，返回 ResponseData。网络/超时异常会向上抛出."""
        variables = variables or {}
        method = request_def.method.upper()

        url = self._render_str(request_def.url, variables)

        # SEC-05: URL 出站策略校验
        if self._url_policy is not None:
            ok, reason = self._url_policy.validate(url)
            if not ok:
                raise ValidationError(f"URL 策略拒绝: {reason}")

        headers = self._render_mapping(request_def.headers, variables)
        params = self._render_mapping(request_def.params, variables)

        request_kwargs: dict[str, Any] = {"headers": headers, "params": params}
        self._fill_body(request_kwargs, request_def, variables)

        # FIX-03: follow_redirects=False，手动处理重定向以重新校验 URL
        client_kwargs: dict[str, Any] = {
            "timeout": request_def.timeout,
            "follow_redirects": False,
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        with httpx.Client(**client_kwargs) as client:
            start = time.perf_counter()
            resp = client.request(method=method, url=url, **request_kwargs)

            # 手动处理重定向：每次重定向重新校验 URL（SSRF 防护）
            redirects = 0
            while resp.is_redirect and redirects < self._max_redirects:
                redirects += 1
                location = resp.headers.get("location")
                if not location:
                    break
                redirect_url = str(httpx.URL(url).join(location))
                if self._url_policy is not None:
                    ok, reason = self._url_policy.validate(redirect_url)
                    if not ok:
                        raise ValidationError(f"URL 策略拒绝: {reason}")
                # 重定向使用 GET，不重发 body
                resp = client.request(
                    method="GET", url=redirect_url, headers=headers
                )
                url = redirect_url

            elapsed = time.perf_counter() - start

        # FIX-03: 响应体大小限制
        if len(resp.content) > self._max_response_size:
            raise ValidationError(
                f"响应体过大: {len(resp.content)} bytes "
                f"(上限 {self._max_response_size} bytes)"
            )

        return self._build_response(resp, elapsed)

    # ---------------- body 组装 ----------------
    def _fill_body(self, kwargs: dict, request_def: RequestDefinition, variables: dict) -> None:
        # GraphQL 优先：POST，body = {"query": ..., "variables": ...}
        if request_def.graphql_query:
            variables_payload = (
                self._render_obj(request_def.body, variables)
                if isinstance(request_def.body, dict)
                else (request_def.body or {})
            )
            kwargs["json"] = {"query": request_def.graphql_query, "variables": variables_payload}
            return

        # 文件上传：multipart，body 作为表单字段
        if request_def.files:
            kwargs["files"] = self._convert_files(request_def.files)
            if isinstance(request_def.body, dict):
                kwargs["data"] = self._render_mapping(request_def.body, variables)
            return

        # 表单 urlencoded
        if self._is_form_urlencoded(request_def.headers):
            if request_def.body is not None:
                kwargs["data"] = self._render_obj(request_def.body, variables)
            return

        # 默认 JSON body
        if request_def.body is not None:
            kwargs["json"] = self._render_obj(request_def.body, variables)

    @staticmethod
    def _convert_files(files: list[dict]) -> list:
        """将文件字典列表转为 httpx 接受的 files 格式.

        每项：{"field": "upload", "filename": "a.txt", "content": "...", "content_type": "text/plain"}
        """
        converted = []
        for f in files:
            field = f.get("field") or f.get("name")
            if not field:
                continue
            filename = f.get("filename", "file")
            content = f.get("content", "")
            content_type = f.get("content_type")
            if content_type:
                converted.append((field, (filename, content, content_type)))
            else:
                converted.append((field, (filename, content)))
        return converted

    @staticmethod
    def _is_form_urlencoded(headers: dict[str, str]) -> bool:
        for key, value in (headers or {}).items():
            if key.lower() == "content-type":
                return "application/x-www-form-urlencoded" in value.lower()
        return False

    # ---------------- 响应构建 ----------------
    @staticmethod
    def _build_response(resp: httpx.Response, elapsed: float) -> ResponseData:
        # 优先按 JSON 解析 body，失败则保留原始文本
        try:
            body: Any = resp.json()
        except (ValueError, Exception):
            body = resp.text
        return ResponseData(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            body=body,
            elapsed=elapsed,
            text=resp.text,
        )

    # ---------------- 模板渲染 ----------------
    @classmethod
    def _render_str(cls, value: str, variables: dict) -> str:
        if not isinstance(value, str):
            return value

        def repl(match: re.Match) -> str:
            key = match.group(1)
            if key in variables:
                return str(variables[key])
            # 未知变量保持原样
            return match.group(0)

        return _VAR_PATTERN.sub(repl, value)

    @classmethod
    def _render_mapping(cls, mapping: dict | None, variables: dict) -> dict:
        if not mapping:
            return {}
        return {k: cls._render_obj(v, variables) for k, v in mapping.items()}

    @classmethod
    def _render_obj(cls, obj: Any, variables: dict) -> Any:
        if isinstance(obj, str):
            return cls._render_str(obj, variables)
        if isinstance(obj, dict):
            return {k: cls._render_obj(v, variables) for k, v in obj.items()}
        if isinstance(obj, list):
            return [cls._render_obj(v, variables) for v in obj]
        return obj
