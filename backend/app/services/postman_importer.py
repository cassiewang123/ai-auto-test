"""Postman Collection v2.x 导入器.

将 Postman Collection 的请求树转换为系统 TestCase 结构：
    - 保留 {{variable}} 模板，交由执行期的全局/环境/用例变量渲染
    - 支持集合变量、文件夹变量、环境变量覆盖
    - 支持 JSON、raw、urlencoded、formdata 请求体
    - 自动补充 epToken 等默认请求头，生成基础状态码断言

设计说明：Postman 集合通常只描述请求，不包含响应定义；因此导入时不生成响应体断言，
只生成状态码断言，后续可在用例管理中继续补充。
"""
from __future__ import annotations

import json
import re
from typing import Any

# Postman 变量占位符，如 {{contentHost}}
_VARIABLE_PATTERN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
_SUPPORTED_SCHEMA_PREFIX = "https://schema.getpostman.com/json/collection/v2"
_SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_UPLOAD_PLACEHOLDER = "{{upload_file}}"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_variables(raw: Any) -> dict[str, str]:
    """解析 Postman 的 variable 列表为字典."""
    variables: dict[str, str] = {}
    if isinstance(raw, dict):
        # 环境文件格式：{"epToken": {"value": "..."}} 或 {"epToken": "..."}
        for key, value in raw.items():
            if isinstance(value, dict):
                variables[str(key)] = _clean_text(value.get("value"))
            else:
                variables[str(key)] = _clean_text(value)
        return variables
    if not isinstance(raw, list):
        return variables
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = _clean_text(item.get("key"))
        if not key:
            continue
        # 已禁用的变量不参与覆盖
        if item.get("disabled") is True:
            continue
        value = item.get("value", item.get("default", ""))
        if isinstance(value, (dict, list)):
            variables[key] = json.dumps(value, ensure_ascii=False)
        else:
            variables[key] = _clean_text(value)
    return variables


def _variable_names(text: str) -> list[str]:
    return [match.strip() for match in _VARIABLE_PATTERN.findall(text or "")]


def _collect_unresolved(value: Any, variables: dict[str, str]) -> list[str]:
    """收集文本中未能在变量表中解析出非空值的变量名."""
    if isinstance(value, dict):
        found: list[str] = []
        for item in value.values():
            for name in _collect_unresolved(item, variables):
                if name not in found:
                    found.append(name)
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            for name in _collect_unresolved(item, variables):
                if name not in found:
                    found.append(name)
        return found
    if not isinstance(value, str):
        return []
    missing: list[str] = []
    for name in _variable_names(value):
        if name in variables and variables[name] != "":
            continue
        if name not in missing:
            missing.append(name)
    return missing


def _url_raw(url: Any) -> str:
    if isinstance(url, str):
        return url
    if isinstance(url, dict):
        return _clean_text(url.get("raw"))
    return ""


def _url_query(url: Any) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if not isinstance(url, dict):
        return params
    for item in url.get("query") or []:
        if not isinstance(item, dict) or item.get("disabled") is True:
            continue
        key = _clean_text(item.get("key"))
        if key:
            params[key] = item.get("value", "")
    return params


def _parse_headers(raw: Any) -> dict[str, str]:
    headers: dict[str, str] = {}
    if isinstance(raw, dict):
        return {str(key): _clean_text(value) for key, value in raw.items()}
    if not isinstance(raw, list):
        return headers
    for item in raw:
        if not isinstance(item, dict) or item.get("disabled") is True:
            continue
        key = _clean_text(item.get("key"))
        if key:
            headers[key] = _clean_text(item.get("value"))
    return headers


def _parse_body(raw: Any) -> Any:
    """转换 Postman body 为系统可存储的 body / files."""
    if not isinstance(raw, dict) or not raw:
        return None, None
    mode = raw.get("mode")
    if mode == "raw":
        text = raw.get("raw") or ""
        if not text.strip():
            return None, None
        try:
            return json.loads(text), None
        except (json.JSONDecodeError, ValueError):
            return text, None
    if mode == "urlencoded":
        data = {
            _clean_text(item.get("key")): item.get("value", "")
            for item in raw.get("urlencoded") or []
            if isinstance(item, dict)
            and item.get("disabled") is not True
            and _clean_text(item.get("key"))
        }
        return (data or None), None
    if mode == "formdata":
        form_data: dict[str, Any] = {}
        files: list[dict[str, Any]] = []
        for item in raw.get("formdata") or []:
            if not isinstance(item, dict) or item.get("disabled") is True:
                continue
            key = _clean_text(item.get("key"))
            if not key:
                continue
            if item.get("type") == "file":
                files.append(
                    {
                        "field": key,
                        "path": item.get("src") or _UPLOAD_PLACEHOLDER,
                    }
                )
            else:
                form_data[key] = item.get("value", "")
        return (form_data or None), (files or None)
    if mode == "graphql":
        graphql = raw.get("graphql") or {}
        return graphql.get("variables") or {}, None
    if mode == "file":
        return None, [{"field": "file", "path": raw.get("file", {}).get("src") or _UPLOAD_PLACEHOLDER}]
    return None, None


class PostmanImporter:
    """Postman Collection v2.x 解析器."""

    def __init__(
        self,
        collection: dict,
        variables: dict[str, Any] | None = None,
        default_headers: dict[str, Any] | None = None,
    ):
        if not isinstance(collection, dict):
            raise ValueError("Postman 集合必须是 JSON 对象")
        self.collection = collection
        self.variables = {str(k): _clean_text(v) for k, v in (variables or {}).items()}
        self.default_headers = {
            str(key): _clean_text(value) for key, value in (default_headers or {}).items()
        }
        self.warnings: list[str] = []

    # ------------------------------------------------------------------
    # 解析入口
    # ------------------------------------------------------------------
    def parse(self) -> list[dict]:
        schema = _clean_text((self.collection.get("info") or {}).get("schema"))
        if schema and not schema.startswith(_SUPPORTED_SCHEMA_PREFIX):
            raise ValueError(f"仅支持 Postman Collection v2.x，当前 schema：{schema}")

        items = self.collection.get("item")
        if not isinstance(items, list):
            raise ValueError("集合缺少 item 请求列表")

        collection_variables = _extract_variables(self.collection.get("variable"))
        merged_variables = {**collection_variables, **self.variables}
        endpoints: list[dict] = []
        self._walk(
            items,
            folder_path=[],
            folder_variables=merged_variables,
            endpoints=endpoints,
        )
        return endpoints

    def merged_variables(self) -> dict[str, str]:
        """返回集合变量与调用方变量合并后的结果（供导入为全局变量）."""
        return {**_extract_variables(self.collection.get("variable")), **self.variables}

    # ------------------------------------------------------------------
    # 递归遍历
    # ------------------------------------------------------------------
    def _walk(
        self,
        items: list,
        folder_path: list[str],
        folder_variables: dict[str, str],
        endpoints: list[dict],
    ) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _clean_text(item.get("name")) or "未命名"
            scoped_variables = {
                **folder_variables,
                **_extract_variables(item.get("variable")),
            }
            if isinstance(item.get("item"), list):
                self._walk(
                    item["item"],
                    [*folder_path, name],
                    scoped_variables,
                    endpoints,
                )
                continue

            request = item.get("request")
            if request is None:
                continue
            endpoint = self._build_endpoint(name, folder_path, request, scoped_variables)
            if endpoint:
                endpoints.append(endpoint)

    # ------------------------------------------------------------------
    # 单个请求转换
    # ------------------------------------------------------------------
    def _build_endpoint(
        self,
        name: str,
        folder_path: list[str],
        request: Any,
        variables: dict[str, str],
    ) -> dict | None:
        if isinstance(request, str):
            request = {"method": "GET", "url": request}
        if not isinstance(request, dict):
            return None

        method = _clean_text(request.get("method") or "GET").upper()
        if method not in _SUPPORTED_METHODS:
            self.warnings.append(f"{name}：暂不支持的方法 {method}，已跳过")
            return None

        url = _url_raw(request.get("url"))
        if not url:
            self.warnings.append(f"{name}：缺少 URL，已跳过")
            return None

        headers = _parse_headers(request.get("header"))
        for key, value in self.default_headers.items():
            headers.setdefault(key, value)
        # 集合级脚本通过 pm.request.headers 注入的 header 不会写入 item，这里按集合变量补齐
        if "epToken" in variables and "epToken" not in headers:
            headers["epToken"] = "{{epToken}}"

        body, files = _parse_body(request.get("body"))
        params = _url_query(request.get("url"))
        group_path = "/".join(folder_path)
        key = f"{method} {url}"

        unresolved: list[str] = []
        for candidate in (url, *headers.values(), body):
            for variable in _collect_unresolved(candidate, variables):
                if variable not in unresolved:
                    unresolved.append(variable)

        return {
            "key": key,
            "name": name,
            "suggested_name": name,
            "method": method,
            "url": url,
            "path": url,
            "full_url": url,
            "group_path": group_path,
            "headers": headers,
            "params": params,
            "body": body,
            "files": files,
            "variables": unresolved,
            "resolved_variables": dict(variables),
            "has_upload": bool(files),
        }


def parse_postman_collection(
    collection: dict,
    variables: dict[str, Any] | None = None,
    default_headers: dict[str, Any] | None = None,
) -> tuple[list[dict], list[str], dict[str, str]]:
    """解析 Postman 集合.

    Returns:
        (endpoints, warnings, merged_variables)
    """
    importer = PostmanImporter(
        collection,
        variables=variables,
        default_headers=default_headers,
    )
    endpoints = importer.parse()
    return endpoints, importer.warnings, importer.merged_variables()
