"""接口导入 API：从 OpenAPI/Swagger 规范批量生成测试用例.

端点：
    POST /api/v1/import/openapi  — 解析 OpenAPI JSON 并批量创建用例
    POST /api/v1/import/preview  — 预览解析结果（不创建）
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.test_case import AssertionRule, TestCase
from app.schemas.common import DataResponse

router = APIRouter()


class ImportRequest(BaseModel):
    """导入请求：提供 URL 或直接提供 OpenAPI JSON."""

    # OpenAPI 文档的 URL（与 spec 二选一）
    url: str | None = None
    # 直接提供 OpenAPI JSON 字典（与 url 二选一）
    spec: dict | None = None
    # 基础 URL：用于测试用例的请求地址前缀（如 http://localhost:8000）
    base_url: str = "http://localhost:8000"
    # 是否只预览不创建
    preview_only: bool = False
    # 要导入的路径前缀筛选（空则全部导入）
    path_prefix: str = ""


class ParsedEndpoint:
    """从 OpenAPI 解析出的单个端点信息."""

    def __init__(self, method: str, path: str, operation: dict, spec: dict):
        self.method = method.upper()
        self.path = path
        self.operation = operation
        self.spec = spec
        self.summary = operation.get("summary", "")
        self.description = operation.get("description", "")
        self.tags = operation.get("tags", [])
        self.parameters = operation.get("parameters", [])
        self.request_body = operation.get("requestBody", {})
        self.responses = operation.get("responses", {})

    def build_url(self, base_url: str) -> str:
        """构建完整 URL，路径参数用占位符替换."""
        url = self.path
        # 路径参数 {id} → {{id}}（模板变量语法）
        for param in self.parameters:
            if param.get("in") == "path":
                name = param.get("name", "id")
                url = url.replace(f"{{{name}}}", f"{{{{{name}}}}}")
        return f"{base_url.rstrip('/')}{url}"

    def build_headers(self) -> dict[str, str]:
        """根据参数生成默认 headers."""
        headers = {"Content-Type": "application/json"}
        for param in self.parameters:
            if param.get("in") == "header":
                pass  # 保留默认
        return headers

    def build_params(self) -> dict[str, Any]:
        """根据 query 参数生成默认 params."""
        params = {}
        for param in self.parameters:
            if param.get("in") == "query":
                name = param.get("name", "")
                schema = param.get("schema", {})
                # 根据类型给默认值
                if schema.get("type") == "integer":
                    params[name] = 1
                elif schema.get("type") == "string":
                    params[name] = "test"
                elif schema.get("type") == "boolean":
                    params[name] = True
                else:
                    params[name] = ""
        return params

    def _generate_example_from_schema(self, schema: dict, spec: dict) -> Any:
        """根据 JSON Schema 递归生成示例值."""
        if not schema:
            return {}
        if "$ref" in schema:
            # 解析 $ref 引用
            ref_path = schema["$ref"].lstrip("#/").split("/")
            ref_schema = spec
            for part in ref_path:
                ref_schema = ref_schema.get(part, {})
            return self._generate_example_from_schema(ref_schema, spec)

        schema_type = schema.get("type", "object")

        if schema.get("example") is not None:
            return schema["example"]

        if schema_type == "string":
            fmt = schema.get("format", "")
            if fmt == "email":
                return "test@example.com"
            if fmt in ("uuid",):
                return "00000000-0000-0000-0000-000000000000"
            if fmt in ("date",):
                return "2026-01-01"
            if fmt in ("date-time",):
                return "2026-01-01T00:00:00Z"
            return "test_string"
        elif schema_type == "integer":
            return 1
        elif schema_type == "number":
            return 1.0
        elif schema_type == "boolean":
            return True
        elif schema_type == "array":
            item_schema = schema.get("items", {})
            return [self._generate_example_from_schema(item_schema, spec)]
        elif schema_type == "object":
            result = {}
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                result[prop_name] = self._generate_example_from_schema(prop_schema, spec)
            return result
        return {}

    def build_body(self) -> dict | None:
        """根据 requestBody 生成默认 body."""
        if not self.request_body:
            return None
        content = self.request_body.get("content", {})
        json_content = content.get("application/json", {})
        if json_content:
            schema = json_content.get("schema", {})
            if schema:
                return self._generate_example_from_schema(schema, self.spec)
        return None

    def build_assertions(self) -> list[dict]:
        """根据响应定义生成默认断言规则."""
        assertions = []
        # 取第一个 2xx 响应码作为期望
        for code, resp in self.responses.items():
            if code.startswith("2"):
                assertions.append({
                    "assertion_type": "status_code",
                    "expression": None,
                    "operator": "eq",
                    "expected": str(code),
                    "priority": "P0",
                    "order": 0,
                })
                break
        if not assertions:
            assertions.append({
                "assertion_type": "status_code",
                "expression": None,
                "operator": "eq",
                "expected": "200",
                "priority": "P0",
                "order": 0,
            })
        return assertions

    def build_group_path(self) -> str:
        """根据 tags 或 path 前缀生成分组路径."""
        if self.tags:
            return "/".join(self.tags)
        # 从 path 提取前两级作为分组
        parts = [p for p in self.path.strip("/").split("/") if not p.startswith("{")]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return parts[0] if parts else "未分组"

    def to_case_dict(self, base_url: str) -> dict:
        """转换为测试用例字典."""
        title = self.summary or f"{self.method} {self.path}"
        return {
            "title": title,
            "description": self.description or f"{self.method} {self.path}",
            "group_path": self.build_group_path(),
            "markers": ["api", "imported"],
            "method": self.method,
            "url": self.build_url(base_url),
            "headers": self.build_headers(),
            "params": self.build_params(),
            "body": self.build_body(),
            "assertions": self.build_assertions(),
        }


def parse_openapi(spec: dict, base_url: str, path_prefix: str = "") -> list[dict]:
    """解析 OpenAPI 规范，返回测试用例字典列表."""
    paths = spec.get("paths", {})
    cases = []
    for path, methods in paths.items():
        if path_prefix and not path.startswith(path_prefix):
            continue
        for method, operation in methods.items():
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            endpoint = ParsedEndpoint(method, path, operation, spec)
            cases.append(endpoint.to_case_dict(base_url))
    return cases


@router.post("/preview", response_model=DataResponse[dict])
def preview_import(req: ImportRequest):
    """预览解析结果，不创建用例."""
    # 获取 spec
    if req.spec:
        spec = req.spec
    elif req.url:
        try:
            with urllib.request.urlopen(req.url, timeout=15) as resp:
                spec = json.loads(resp.read().decode())
        except Exception as exc:
            return DataResponse(data={"error": f"获取 OpenAPI 文档失败: {exc}"})
    else:
        return DataResponse(data={"error": "请提供 url 或 spec"})

    cases = parse_openapi(spec, req.base_url, req.path_prefix)
    return DataResponse(data={
        "total": len(cases),
        "endpoints": cases,
    })


@router.post("/openapi", response_model=DataResponse[dict])
def import_openapi(req: ImportRequest, db: Session = Depends(get_db)):
    """解析 OpenAPI 规范并批量创建测试用例."""
    # 获取 spec
    if req.spec:
        spec = req.spec
    elif req.url:
        try:
            with urllib.request.urlopen(req.url, timeout=15) as resp:
                spec = json.loads(resp.read().decode())
        except Exception as exc:
            return DataResponse(data={"error": f"获取 OpenAPI 文档失败: {exc}"})
    else:
        return DataResponse(data={"error": "请提供 url 或 spec"})

    cases = parse_openapi(spec, req.base_url, req.path_prefix)

    if req.preview_only:
        return DataResponse(data={"total": len(cases), "endpoints": cases, "created": 0})

    # 批量创建
    created_ids = []
    for case_data in cases:
        assertions_data = case_data.pop("assertions", [])
        case = TestCase(**case_data)
        db.add(case)
        db.flush()  # 获取 case.id

        for a in assertions_data:
            assertion = AssertionRule(
                test_case_id=case.id,
                assertion_type=a["assertion_type"],
                expression=a.get("expression"),
                operator=a["operator"],
                expected=a.get("expected"),
                priority=a.get("priority", "P1"),
                order=a.get("order", 0),
            )
            db.add(assertion)

        created_ids.append(case.id)

    db.commit()

    return DataResponse(data={
        "total": len(cases),
        "created": len(created_ids),
        "case_ids": created_ids,
        "endpoints": cases,
    })


# ---------------------------------------------------------------------------
# HAR 抓包导入
# ---------------------------------------------------------------------------
class HarPreviewRequest(BaseModel):
    har_content: dict          # HAR 文件 JSON 内容
    domain_filter: str | None = None
    method_filter: str | None = None


class HarImportRequest(BaseModel):
    selected_interfaces: list[dict]  # 选中的接口列表
    project_id: str | None = None


def _parse_path(url: str) -> str:
    """从完整 URL 中提取路径部分."""
    parsed = urlparse(url)
    return parsed.path


def _parse_headers(headers_list: list) -> dict:
    """HAR headers 是 [{name, value}] 列表，转为 dict.
    过滤掉 cookie 和 content-length."""
    return {h["name"]: h["value"] for h in headers_list
            if h.get("name", "").lower() not in ("cookie", "content-length")}


def _parse_query(query_string_list: list) -> dict:
    """HAR queryString 是 [{name, value}] 列表，转为 dict."""
    return {q["name"]: q["value"] for q in query_string_list}


def _parse_body(post_data: dict) -> dict | None:
    """解析 HAR postData 为 body dict."""
    if not post_data:
        return None
    text = post_data.get("text", "")
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"text": text}


def _parse_response_body(response: dict) -> dict | None:
    """解析 HAR response body."""
    content = response.get("content", {})
    text = content.get("text", "")
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _suggest_name(method: str, path: str) -> str:
    """根据方法和路径推断接口名称."""
    path_map = {
        "login": "登录", "logout": "登出", "register": "注册",
        "users": "用户", "orders": "订单", "products": "商品",
        "create": "创建", "delete": "删除", "update": "更新",
        "list": "列表", "detail": "详情", "search": "搜索",
    }
    name_parts = []
    for key, cn in path_map.items():
        if key in path.lower():
            name_parts.append(cn)
    method_map = {"GET": "查询", "POST": "创建", "PUT": "更新", "DELETE": "删除", "PATCH": "修改"}
    action = method_map.get(method, method)
    return f"{action}{''.join(name_parts) or '接口'}"


def _auto_generate_assertions(iface: dict) -> list[dict]:
    """根据 HAR 响应状态码自动生成基础断言."""
    status = iface.get("response_status", 200)
    return [{
        "assertion_type": "status_code",
        "operator": "eq",
        "expected": str(status) if status else "200",
        "priority": "P0",
        "order": 0,
    }]


def _build_iface(entry: dict) -> dict:
    """从 HAR entry 构建接口预览字典."""
    req = entry.get("request", {})
    resp = entry.get("response", {})
    url = req.get("url", "")
    method = req.get("method", "GET")
    path = _parse_path(url)
    return {
        "key": f"{method} {path}",
        "method": method,
        "path": path,
        "full_url": url,
        "headers": _parse_headers(req.get("headers", [])),
        "params": _parse_query(req.get("queryString", [])),
        "body": _parse_body(req.get("postData", {})),
        "response_status": resp.get("status", 0),
        "response_body": _parse_response_body(resp),
        "suggested_name": _suggest_name(method, path),
    }


@router.post("/har/preview", response_model=DataResponse[dict])
def preview_har(payload: HarPreviewRequest, db: Session = Depends(get_db)):
    """解析 HAR 文件，返回接口预览列表."""
    entries = payload.har_content.get("log", {}).get("entries", [])
    interfaces = []
    seen_urls = set()
    for entry in entries:
        req = entry.get("request", {})
        url = req.get("url", "")
        method = req.get("method", "GET")
        # 域名筛选
        if payload.domain_filter and payload.domain_filter not in url:
            continue
        if payload.method_filter and method != payload.method_filter:
            continue
        # 去重（同 method+path 只保留最后一次）
        key = f"{method} {_parse_path(url)}"
        iface = _build_iface(entry)
        if key in seen_urls:
            # 更新已有记录为最后一次出现
            for i, existing in enumerate(interfaces):
                if existing.get("key") == key:
                    interfaces[i] = iface
                    break
            continue
        seen_urls.add(key)
        interfaces.append(iface)
    return DataResponse(data={"interfaces": interfaces, "total": len(interfaces)})


@router.post("/har/import", response_model=DataResponse[dict])
def import_har(payload: HarImportRequest, db: Session = Depends(get_db)):
    """将选中的 HAR 接口批量创建为 TestCase."""
    created_ids = []
    for iface in payload.selected_interfaces:
        case = TestCase(
            title=iface.get("suggested_name", iface.get("path", "未命名接口")),
            method=iface["method"],
            url=iface.get("path", iface.get("full_url", "")),
            headers=iface.get("headers", {}),
            params=iface.get("params", {}),
            body=iface.get("body"),
            project_id=payload.project_id,
            markers=["api", "har_imported"],
        )
        db.add(case)
        db.flush()
        # 自动生成基础断言
        for a in _auto_generate_assertions(iface):
            db.add(AssertionRule(test_case_id=case.id, **a))
        created_ids.append(case.id)
    db.commit()
    return DataResponse(data={"created_count": len(created_ids), "case_ids": created_ids})
