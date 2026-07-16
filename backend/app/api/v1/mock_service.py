"""Mock 服务 API：Mock 配置 CRUD + Mock 请求处理端点（含 Phase 4 故障注入/动态响应/优先级匹配）."""
from __future__ import annotations

import json
import random
import re
import time

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.mock_config import MockConfig
from app.schemas.common import DataResponse, PageResponse
from app.schemas.mock import (
    FaultInjectionSpec,
    MockConfigCreate,
    MockConfigResponse,
    MockConfigUpdate,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# 序列化与工具函数
# ---------------------------------------------------------------------------


def _safe_json_loads(text: str | None) -> dict | None:
    """安全解析 JSON 字符串；解析失败返回 None。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _safe_fault_injection(text: str | None) -> dict:
    """解析故障注入配置，返回字段齐全的 dict（缺失字段使用默认值）。"""
    defaults = {
        "delay_ms": 0,
        "timeout": False,
        "disconnect": False,
        "error_rate": 0,
        "error_status": 500,
        "rate_limit": None,
    }
    parsed = _safe_json_loads(text)
    if not isinstance(parsed, dict):
        return defaults
    for k, v in defaults.items():
        parsed.setdefault(k, v)
    return parsed


def _serialize_config(c: MockConfig) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "method": c.method,
        "path": c.path,
        "status_code": c.status_code,
        "response_headers": c.response_headers,
        "response_body": c.response_body,
        "delay_ms": c.delay_ms,
        "is_enabled": c.is_enabled,
        "project_id": c.project_id,
        # Phase 4 新增字段
        "response_template": c.response_template,
        "match_rules": _safe_json_loads(c.match_rules),
        "priority": c.priority,
        "stateful_config": _safe_json_loads(c.stateful_config),
        "fault_injection": _safe_fault_injection(c.fault_injection),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _normalize_path(path: str) -> str:
    """归一化路径：去除首尾斜杠，便于匹配."""
    return path.strip().strip("/")


def _build_request_context(request: Request) -> dict:
    """构建用于模板替换与匹配的请求上下文 dict.

    返回结构示例：
        {
            "method": "POST",
            "url": "/mock/foo?x=1",
            "path": "/mock/foo",
            "query": {"x": "1"},
            "headers": {"x-custom": "...", "content-type": "..."},
            "body": {...} | None,
        }
    """
    # headers 转小写键，便于 case-insensitive 访问
    headers = {k.lower(): v for k, v in request.headers.items()}
    # query params（多值取第一个）
    query = {k: v for k, v in request.query_params.items()}
    body: dict | None = None
    try:
        raw_body = request._body  # type: ignore[attr-defined]
    except AttributeError:
        raw_body = None
    if raw_body:
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            if isinstance(parsed, dict):
                body = parsed
            elif isinstance(parsed, list):
                body = {"_list": parsed}
        except (ValueError, TypeError, UnicodeDecodeError):
            body = None
    return {
        "method": request.method,
        "url": str(request.url),
        "path": request.url.path,
        "query": query,
        "headers": headers,
        "body": body or {},
    }


def _get_nested(ctx: dict, dotted_key: str):
    """从上下文中按点分路径取值。

    支持形如：
      - "request.body.user_id"
      - "request.headers.x-custom"
      - "request.query.page"
    """
    parts = dotted_key.split(".")
    current: object = ctx
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _match_rules_satisfied(match_rules: dict | None, ctx: dict) -> bool:
    """检查请求上下文是否满足 match_rules 中的所有约束。

    match_rules 形如 {"request.headers.x-custom": "abc", "request.body.user_id": 123}
    缺失字段或值不匹配时返回 False。
    """
    if not match_rules:
        return True
    for key, expected in match_rules.items():
        actual = _get_nested(ctx, key)
        if actual is None:
            return False
        # 类型宽松比较：字符串化后比较
        if str(actual) != str(expected):
            return False
    return True


# 简单变量替换正则：匹配 {{ namespace.path }}
_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([\w.\-]+)\s*\}\}")


def _render_template(template: str, ctx: dict) -> str:
    """对模板做简单变量替换。

    支持 {{request.body.field}}、{{request.headers.x-custom}}、{{request.query.page}} 等。
    未匹配到值的占位符替换为空字符串。
    """
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = _get_nested(ctx, key)
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return _TEMPLATE_VAR_RE.sub(_replace, template)


def _dump_json_field(value) -> str | None:
    """将 dict/list 序列化为 JSON 文本；None 保持 None。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Mock 配置 CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=PageResponse[dict])
def list_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Mock 配置列表分页."""
    total = db.execute(select(func.count()).select_from(MockConfig)).scalar_one()
    configs = (
        db.execute(
            select(MockConfig)
            .order_by(MockConfig.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_config(c) for c in configs]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("", response_model=DataResponse[dict])
def create_config(payload: MockConfigCreate, db: Session = Depends(get_db)):
    """创建 Mock 配置（含 Phase 4 故障注入/动态响应字段）."""
    data = payload.model_dump()
    # dict/list 类字段序列化为 JSON 文本存储（模型对应字段是 Text）
    data["match_rules"] = _dump_json_field(data.get("match_rules"))
    data["stateful_config"] = _dump_json_field(data.get("stateful_config"))
    data["fault_injection"] = _dump_json_field(data.get("fault_injection"))
    config = MockConfig(**data)
    db.add(config)
    db.commit()
    db.refresh(config)
    return DataResponse(data={"id": config.id, "name": config.name})


@router.get("/{config_id}", response_model=DataResponse[dict])
def get_config(config_id: str, db: Session = Depends(get_db)):
    """获取单个 Mock 配置."""
    config = db.get(MockConfig, config_id)
    if not config:
        raise NotFoundError("Mock 配置", config_id)
    return DataResponse(data=_serialize_config(config))


@router.put("/{config_id}", response_model=DataResponse[dict])
def update_config(config_id: str, payload: MockConfigUpdate, db: Session = Depends(get_db)):
    """更新 Mock 配置（含 Phase 4 增强字段）."""
    config = db.get(MockConfig, config_id)
    if not config:
        raise NotFoundError("Mock 配置", config_id)
    data = payload.model_dump(exclude_unset=True)
    # dict/list 类字段序列化为 JSON 文本存储
    if "match_rules" in data:
        data["match_rules"] = _dump_json_field(data["match_rules"])
    if "stateful_config" in data:
        data["stateful_config"] = _dump_json_field(data["stateful_config"])
    if "fault_injection" in data:
        data["fault_injection"] = _dump_json_field(data["fault_injection"])
    for field, value in data.items():
        setattr(config, field, value)
    db.commit()
    return DataResponse(data={"id": config.id, "name": config.name})


@router.delete("/{config_id}", response_model=DataResponse[dict])
def delete_config(config_id: str, db: Session = Depends(get_db)):
    """删除 Mock 配置."""
    config = db.get(MockConfig, config_id)
    if not config:
        raise NotFoundError("Mock 配置", config_id)
    db.delete(config)
    db.commit()
    return DataResponse(data={"id": config_id, "deleted": True})


@router.post("/{config_id}/toggle", response_model=DataResponse[dict])
def toggle_config(config_id: str, db: Session = Depends(get_db)):
    """启用/停用 Mock 配置."""
    config = db.get(MockConfig, config_id)
    if not config:
        raise NotFoundError("Mock 配置", config_id)
    config.is_enabled = not config.is_enabled
    db.commit()
    return DataResponse(data={"id": config.id, "is_enabled": config.is_enabled})


# ---------------------------------------------------------------------------
# Mock 请求处理端点（通配路由）—— Phase 4 增强：优先级 / match_rules / 故障注入 / 模板
# ---------------------------------------------------------------------------

@router.api_route(
    "/mock/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
def handle_mock_request(path: str, request: Request, db: Session = Depends(get_db)):
    """根据 method + path 匹配 MockConfig，返回配置的响应.

    Phase 4 增强：
    - 按 priority 降序匹配，最先匹配到的配置生效
    - 支持 match_rules：基于请求头/查询参数/请求体字段进一步过滤
    - 支持故障注入：delay_ms / timeout / disconnect / error_rate
    - 支持响应模板变量替换 {{request.body.field}} / {{request.headers.x-custom}}
    """
    normalized = _normalize_path(path)
    ctx = _build_request_context(request)

    configs = (
        db.execute(
            select(MockConfig).where(MockConfig.is_enabled.is_(True))
        )
        .scalars()
        .all()
    )

    # 按 priority 降序排序，priority 相同时保持数据库返回顺序
    configs_sorted = sorted(configs, key=lambda c: c.priority or 0, reverse=True)

    matched = None
    for c in configs_sorted:
        if c.method.upper() != request.method.upper():
            continue
        if _normalize_path(c.path) != normalized:
            continue
        # 检查 match_rules 是否满足
        match_rules = _safe_json_loads(c.match_rules)
        if not _match_rules_satisfied(match_rules, ctx):
            continue
        matched = c
        break

    if not matched:
        return Response(
            content=json.dumps(
                {"error": "未匹配到 Mock 配置", "method": request.method, "path": f"/{path}"},
                ensure_ascii=False,
            ).encode("utf-8"),
            status_code=404,
            media_type="application/json",
        )

    # --- Phase 4: 故障注入 ---
    fault = _safe_fault_injection(matched.fault_injection)

    # 模拟超时：休眠 30s（接近客户端默认超时），让客户端主动断开
    if fault.get("timeout"):
        # 不返回响应，模拟服务端不响应
        time.sleep(30)
        # 即便客户端没断开，最终也返回 504
        return Response(
            content=json.dumps({"error": "mock timeout"}).encode("utf-8"),
            status_code=504,
            media_type="application/json",
        )

    # 立即断开连接：返回空响应 + 502（Starlette 无法真正 RST，用 502 近似）
    if fault.get("disconnect"):
        return Response(
            content=b"",
            status_code=502,
            media_type="application/json",
        )

    # 故障注入延迟（叠加在 delay_ms 之上）
    fault_delay = fault.get("delay_ms") or 0
    if fault_delay > 0:
        time.sleep(fault_delay / 1000.0)

    # 按概率返回错误状态码
    error_rate = float(fault.get("error_rate") or 0)
    if error_rate > 0:
        if random.random() < error_rate:
            error_status = int(fault.get("error_status") or 500)
            return Response(
                content=json.dumps(
                    {"error": "fault injection", "status": error_status},
                    ensure_ascii=False,
                ).encode("utf-8"),
                status_code=error_status,
                media_type="application/json",
            )

    # --- 基础响应延迟（保留原逻辑） ---
    if matched.delay_ms and matched.delay_ms > 0:
        time.sleep(matched.delay_ms / 1000.0)

    headers = dict(matched.response_headers or {})

    # --- Phase 4: 动态响应模板 ---
    if matched.response_template:
        body = _render_template(matched.response_template, ctx)
    else:
        body = matched.response_body or ""

    # 若未显式指定 Content-Type，尝试推断
    has_content_type = any(k.lower() == "content-type" for k in headers)
    if not has_content_type:
        try:
            json.loads(body)
            headers["Content-Type"] = "application/json"
        except (ValueError, TypeError):
            headers["Content-Type"] = "text/plain"

    return Response(
        content=body.encode("utf-8"),
        status_code=matched.status_code,
        headers=headers,
    )


__all__ = [
    "router",
    "MockConfigCreate",
    "MockConfigUpdate",
    "MockConfigResponse",
    "FaultInjectionSpec",
]
