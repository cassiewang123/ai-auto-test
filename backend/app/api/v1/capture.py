"""页面接口抓取 API：从 Web 页面前端代码中提取 API 接口."""
from __future__ import annotations

import json
import re
import ssl
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.test_case import AssertionRule, TestCase
from app.schemas.common import DataResponse

router = APIRouter()

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# 需要过滤的静态资源后缀
_STATIC_EXTS = {'.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.ico', '.woff', '.ttf', '.gif', '.eot', '.map', '.json', '.html'}

# 需要过滤的 ECharts/UI 配置项前缀
_NOISE_PREFIXES = {
    'align', 'color', 'font', 'size', 'text', 'border', 'background', 'shadow',
    'padding', 'margin', 'width', 'height', 'left', 'right', 'top', 'bottom',
    'show', 'hide', 'type', 'name', 'value', 'data', 'label', 'axis', 'grid',
    'series', 'tooltip', 'legend', 'title', 'item', 'line', 'bar', 'pie', 'area',
    'scale', 'zoom', 'rotate', 'offset', 'position', 'center', 'radius', 'angle',
    'duration', 'delay', 'animation', 'style', 'mode', 'sort', 'order', 'group',
    'level', 'index', 'count', 'start', 'end', 'min', 'max', 'range', 'step',
    'interval', 'gap', 'span', 'split', 'symbol', 'icon', 'image', 'format',
    'render', 'trigger', 'event', 'action', 'state', 'status', 'source',
    'target', 'origin', 'layout', 'design', 'view', 'page', 'component',
    'element', 'node', 'tree', 'list', 'table', 'form', 'input', 'output',
    'select', 'option', 'silent', 'smooth', 'snap', 'stack', 'roam', 'clip',
    'cursor', 'draggable', 'overflow', 'overlap', 'readOnly', 'realtime',
    'inside', 'outside', 'normal', 'enabled', 'disabled', 'fixed', 'focus',
    'blur', 'darkMode', 'aria', 'calculable', 'categorySortInfo',
}


class ScanRequest(BaseModel):
    url: str
    base_url: str = ""


class CapturedEndpoint(BaseModel):
    method: str = "GET"
    url: str
    title: str = ""
    group_path: str = ""
    headers: dict[str, str] = {}
    params: dict[str, Any] = {}
    body: dict | None = None
    source_file: str = ""


class ScanResult(BaseModel):
    total: int = 0
    endpoints: list[dict] = []


class ImportRequest(BaseModel):
    project_id: str
    base_url: str = ""
    endpoints: list[dict]


def _is_noise_path(path: str) -> bool:
    """Check if path is an ECharts/UI config noise."""
    stripped = path.strip("/")
    if not stripped:
        return True
    first = stripped.split("/")[0].lower()
    if first in _NOISE_PREFIXES:
        return True
    # Single-word paths are likely noise
    if "/" not in stripped and len(first) < 8:
        return True
    return False


def _extract_api_paths(js_content: str) -> list[tuple[str, str]]:
    """Extract (method, path) pairs from JS content."""
    results = []
    seen = set()

    patterns = [
        # .get("/path"), .post("/path"), etc.
        (r'\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']{3,200})["\']', True),
        # url: "/path" or url:"/path"
        (r'(?:url|URL|uri|URI)\s*:\s*["\']([^"\']{3,200})["\']', False),
        # request({ url: "/path" })
        (r'request\s*\(\s*\{[^}]*?(?:url|URL)\s*:\s*["\']([^"\']{3,200})["\']', False),
        # $http.get("/path"), axios.post("/path")
        (r'(?:\$http|\$ajax|axios|http|ajax)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*["\']([^"\']{3,200})["\']', True),
    ]

    for pat, has_method in re.finditer if False else patterns:
        for m in re.finditer(pat, js_content, re.IGNORECASE):
            if has_method:
                method = m.group(1).upper()
                path = m.group(2)
            else:
                method = "GET"
                path = m.group(1)

            # Filter static resources
            if any(path.lower().endswith(ext) for ext in _STATIC_EXTS):
                continue
            # Filter non-path strings
            if path.startswith(('data:', 'blob:', 'mailto:', 'javascript:', '#', 'http')):
                continue
            if not path.startswith('/'):
                continue

            key = f"{method} {path}"
            if key not in seen and not _is_noise_path(path):
                seen.add(key)
                results.append((method, path))

    return results


@router.post("/scan", response_model=DataResponse[dict])
def scan_page(req: ScanRequest):
    """扫描 Web 页面，从前端 JS 代码中提取 API 接口路径."""
    base_url = req.base_url or req.url.rstrip("/")

    try:
        page_req = urllib.request.Request(req.url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(page_req, timeout=15, context=_ctx) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return DataResponse(data={"error": f"获取页面失败: {exc}", "total": 0, "endpoints": []})

    # Extract JS file references (handle both quoted and unquoted HTML attributes)
    js_files = set()
    for pat in [r'src=([^"\s>]+\.js[^\s>]*)', r'src=["\']([^"\']+\.js[^"\']*)["\']',
                r'href=([^"\s>]+\.js[^\s>]*)', r'href=["\']([^"\']+\.js[^"\']*)["\']']:
        js_files.update(re.findall(pat, html, re.IGNORECASE))

    # Determine the origin for resolving relative URLs
    from urllib.parse import urlparse
    parsed = urlparse(req.url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    all_endpoints = []
    seen_urls = set()

    for js_file in sorted(js_files):
        # Build full URL
        if js_file.startswith("http"):
            js_url = js_file
        elif js_file.startswith("/"):
            js_url = origin + js_file
        else:
            js_url = req.url.rstrip("/") + "/" + js_file

        fetch_url = js_url.split("?")[0]

        try:
            js_req = urllib.request.Request(fetch_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(js_req, timeout=20, context=_ctx) as resp:
                js_content = resp.read().decode("utf-8", errors="replace")
        except Exception:
            continue

        # Skip very large vendor bundles
        if len(js_content) > 3000000:
            continue

        extracted = _extract_api_paths(js_content)
        for method, path in extracted:
            full_url = base_url.rstrip("/") + path
            endpoint_key = f"{method} {full_url}"
            if endpoint_key in seen_urls:
                continue
            seen_urls.add(endpoint_key)

            # Build group_path from path segments
            parts = [p for p in path.strip("/").split("/") if not p.startswith("{") and not p.startswith(":")]
            group_path = "/".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "未分组")

            all_endpoints.append({
                "method": method,
                "url": full_url,
                "title": f"{method} {path}",
                "group_path": group_path,
                "headers": {"Content-Type": "application/json", "Accept": "application/json"} if method in ("POST", "PUT", "PATCH") else {"Accept": "application/json"},
                "params": {},
                "body": {} if method in ("POST", "PUT", "PATCH") else None,
                "source_file": js_file,
            })

    return DataResponse(data={
        "total": len(all_endpoints),
        "endpoints": all_endpoints,
    })


@router.post("/import", response_model=DataResponse[dict])
def import_captured(req: ImportRequest, db: Session = Depends(get_db)):
    """将抓取到的接口批量导入为测试用例."""
    created_ids = []
    for ep in req.endpoints:
        method = ep.get("method", "GET")
        case = TestCase(
            title=ep.get("title", f"{method} {ep.get('url', '')}"),
            description=f"从页面抓取导入。来源: {ep.get('source_file', '')}",
            group_path=ep.get("group_path", ""),
            markers=["captured"],
            method=method,
            url=ep.get("url", ""),
            headers=ep.get("headers", {}),
            params=ep.get("params", {}),
            body=ep.get("body"),
            project_id=req.project_id,
        )
        db.add(case)
        db.flush()

        # Default assertion: status code 200
        db.add(AssertionRule(
            test_case_id=case.id,
            assertion_type="status_code",
            operator="eq",
            expected="200",
            priority="P0",
            order=0,
        ))
        created_ids.append(case.id)

    db.commit()
    return DataResponse(data={
        "total": len(req.endpoints),
        "created": len(created_ids),
        "case_ids": created_ids,
    })
