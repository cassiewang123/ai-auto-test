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

import base64
import re
import time
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

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
        """渲染变量并发送请求，返回 ResponseData。网络/超时异常会向上抛出.

        渲染后的 url / headers / params 会写回 request_def，便于调用方记录真实请求。
        """
        variables = variables or {}
        method = request_def.method.upper()

        url = self._render_url(request_def.url, variables)

        # SEC-05: URL 出站策略校验
        if self._url_policy is not None:
            ok, reason = self._url_policy.validate(url)
            if not ok:
                raise ValidationError(f"URL 策略拒绝: {reason}")

        headers = self._render_mapping(request_def.headers, variables)
        params = self._render_mapping(request_def.params, variables)
        request_def.url = url
        request_def.headers = headers
        request_def.params = params

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
            # 交给 httpx 生成带 boundary 的 multipart Content-Type，
            # 避免用例里残留的 application/json 导致服务端无法解析文件。
            headers = kwargs.get("headers")
            if isinstance(headers, dict):
                for key in list(headers):
                    if key.lower() == "content-type":
                        headers.pop(key)
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
            encoded = f.get("content_base64")
            if encoded:
                try:
                    content = base64.b64decode(encoded)
                except (ValueError, TypeError):
                    content = ""
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
    _TEXT_CONTENT_TYPES = (
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-www-form-urlencoded",
        "application/graphql",
        "application/yaml",
        "application/x-yaml",
    )

    @classmethod
    def _is_textual_response(cls, resp: httpx.Response) -> bool:
        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type.startswith("text/"):
            return True
        if any(hint in content_type for hint in cls._TEXT_CONTENT_TYPES):
            return True
        if content_type.endswith(("+json", "+xml", "+yaml")):
            return True
        if not content_type:
            try:
                resp.content.decode("utf-8")
            except UnicodeDecodeError:
                return False
            return True
        return False

    @staticmethod
    def _response_filename(resp: httpx.Response) -> str:
        disposition = resp.headers.get("content-disposition") or ""
        match = re.search(r"filename\*=UTF-8''([^;]+)", disposition, re.IGNORECASE)
        if match:
            return unquote(match.group(1).strip().strip('"'))
        match = re.search(r'filename="?([^";]+)"?', disposition, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return "response.bin"

    @staticmethod
    def _infer_binary_metadata(
        resp: httpx.Response, content: bytes
    ) -> tuple[str, str]:
        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
        filename = RequestBuilder._response_filename(resp)
        extension = ""
        sniff = content[:65536]
        if b"xl/workbook.xml" in sniff:
            extension, inferred_type = ".xlsx", (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        elif b"word/document.xml" in sniff:
            extension, inferred_type = ".docx", (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        elif sniff.startswith(b"%PDF"):
            extension, inferred_type = ".pdf", "application/pdf"
        elif sniff.startswith(b"PK\x03\x04"):
            extension, inferred_type = ".zip", "application/zip"
        else:
            inferred_type = ""
        if extension and filename == "response.bin":
            path_name = urlsplit(str(resp.request.url)).path.rstrip("/").split("/")[-1]
            filename = f"{unquote(path_name) or 'response'}{extension}"
        if not content_type or content_type == "application/octet-stream":
            content_type = inferred_type or content_type or "application/octet-stream"
        return filename, content_type

    @classmethod
    def _build_response(cls, resp: httpx.Response, elapsed: float) -> ResponseData:
        if not cls._is_textual_response(resp):
            content = resp.content
            filename, content_type = cls._infer_binary_metadata(resp, content)
            body: Any = {
                "__binary__": True,
                "content_type": content_type,
                "filename": filename,
                "size": len(content),
                "base64": base64.b64encode(content).decode("ascii"),
            }
            text = ""
        else:
            # 优先按 JSON 解析 body，失败则保留原始文本
            try:
                body = resp.json()
            except (ValueError, Exception):
                body = resp.text
            text = resp.text
        return ResponseData(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            body=body,
            elapsed=elapsed,
            text=text,
        )

    # ---------------- 模板渲染 ----------------
    @classmethod
    def _render_url(cls, value: str, variables: dict) -> str:
        """渲染 URL 并规范化路径.

        变量值常带前导/尾随斜杠（如 contentContext=/gateway），与模板中的 "/" 叠加后
        会产生 "//gateway" 这类路径，网关通常会路由失败。
        """
        if not isinstance(value, str):
            return value
        return cls._collapse_path_slashes(cls._render_str(value, variables))

    @staticmethod
    def _collapse_path_slashes(url: str) -> str:
        """合并 URL 路径中的重复斜杠，保留 scheme:// 与查询参数原样."""
        if "://" not in url:
            return re.sub(r"/{2,}", "/", url)
        parts = urlsplit(url)
        path = re.sub(r"/{2,}", "/", parts.path)
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

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
