"""UI 定位器 CRUD + 自动修复建议端点（Phase 4 UI 增强）.

端点：
- GET    /ui-locators            列表（支持 project_id / name_search / page_url 筛选）
- POST   /ui-locators            创建
- GET    /ui-locators/{id}       获取
- PUT    /ui-locators/{id}       更新
- DELETE /ui-locators/{id}       删除
- POST   /ui-locators/{id}/suggest-fix
         基于现有定位器生成修复建议（不自动覆盖，返回建议列表供人工确认）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.ui_locator import UILocator
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class AlternativeSelector(BaseModel):
    """备选定位器条目。"""

    type: str = Field(..., description="css/role/text/test_id/xpath")
    value: str


class UILocatorCreate(BaseModel):
    """创建 UI 定位器。"""

    name: str = Field(..., max_length=200)
    project_id: str | None = None
    page_url: str | None = Field(default=None, max_length=500)
    selector_type: str = Field(default="css", max_length=30)
    selector_value: str = Field(..., max_length=500)
    alternative_selectors: list[AlternativeSelector] | None = None
    description: str | None = None
    is_active: bool = True


class UILocatorUpdate(BaseModel):
    """更新 UI 定位器（部分更新）。"""

    name: str | None = None
    project_id: str | None = None
    page_url: str | None = None
    selector_type: str | None = None
    selector_value: str | None = None
    alternative_selectors: list[AlternativeSelector] | None = None
    description: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------


def _safe_json_loads(text: str | None):
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _serialize_locator(loc: UILocator) -> dict:
    return {
        "id": loc.id,
        "name": loc.name,
        "project_id": loc.project_id,
        "page_url": loc.page_url,
        "selector_type": loc.selector_type,
        "selector_value": loc.selector_value,
        "alternative_selectors": _safe_json_loads(loc.alternative_selectors),
        "description": loc.description,
        "usage_count": loc.usage_count,
        "last_used_at": loc.last_used_at.isoformat() if loc.last_used_at else None,
        "is_active": loc.is_active,
        "created_at": loc.created_at.isoformat() if loc.created_at else None,
        "updated_at": loc.updated_at.isoformat() if loc.updated_at else None,
    }


def _get_or_404(db: Session, locator_id: str) -> UILocator:
    loc = db.get(UILocator, locator_id)
    if not loc:
        raise NotFoundError("UI 定位器", locator_id)
    return loc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=PageResponse[dict])
def list_ui_locators(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    name_search: str | None = Query(None, description="按名称模糊搜索"),
    page_url: str | None = Query(None, description="按页面 URL 模糊搜索"),
    is_active: bool | None = Query(None, description="按启用状态筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """UI 定位器列表分页。"""
    query = select(UILocator)
    count_query = select(func.count()).select_from(UILocator)
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query, UILocator, current_user, owner_field=None
    )
    count_query = scope_project_resources(
        count_query, UILocator, current_user, owner_field=None
    )

    if project_id is not None:
        query = query.where(UILocator.project_id == project_id)
        count_query = count_query.where(UILocator.project_id == project_id)
    if name_search:
        query = query.where(UILocator.name.like(f"%{name_search}%"))
        count_query = count_query.where(UILocator.name.like(f"%{name_search}%"))
    if page_url:
        query = query.where(UILocator.page_url.like(f"%{page_url}%"))
        count_query = count_query.where(UILocator.page_url.like(f"%{page_url}%"))
    if is_active is not None:
        query = query.where(UILocator.is_active.is_(is_active))
        count_query = count_query.where(UILocator.is_active.is_(is_active))

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(UILocator.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_locator(locator) for locator in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("", response_model=DataResponse[dict])
def create_ui_locator(
    payload: UILocatorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建 UI 定位器。"""
    ensure_project_assignment(db, current_user, payload.project_id, "developer")
    data = payload.model_dump()
    if data.get("alternative_selectors") is not None:
        data["alternative_selectors"] = json.dumps(
            data["alternative_selectors"], ensure_ascii=False
        )
    loc = UILocator(**data)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return DataResponse(data=_serialize_locator(loc))


@router.get("/{locator_id}", response_model=DataResponse[dict])
def get_ui_locator(
    locator_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个 UI 定位器。"""
    loc = _get_or_404(db, locator_id)
    ensure_resource_role(db, current_user, loc, "viewer", owner_field=None)
    # 更新使用统计（非关键操作，失败忽略）
    try:
        loc.usage_count = (loc.usage_count or 0) + 1
        loc.last_used_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(loc)
    except Exception:
        db.rollback()
    return DataResponse(data=_serialize_locator(loc))


@router.put("/{locator_id}", response_model=DataResponse[dict])
def update_ui_locator(
    locator_id: str,
    payload: UILocatorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 UI 定位器。"""
    loc = _get_or_404(db, locator_id)
    ensure_resource_role(db, current_user, loc, "developer", owner_field=None)
    data = payload.model_dump(exclude_unset=True)
    if "project_id" in data and data["project_id"] != loc.project_id:
        ensure_resource_role(db, current_user, loc, "admin", owner_field=None)
        ensure_project_assignment(
            db, current_user, data["project_id"], "admin"
        )
    if "alternative_selectors" in data and data["alternative_selectors"] is not None:
        data["alternative_selectors"] = json.dumps(
            data["alternative_selectors"], ensure_ascii=False
        )
    for field, value in data.items():
        setattr(loc, field, value)
    db.commit()
    db.refresh(loc)
    return DataResponse(data=_serialize_locator(loc))


@router.delete("/{locator_id}", response_model=DataResponse[dict])
def delete_ui_locator(
    locator_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 UI 定位器。"""
    loc = _get_or_404(db, locator_id)
    ensure_resource_role(db, current_user, loc, "admin", owner_field=None)
    db.delete(loc)
    db.commit()
    return DataResponse(data={"id": locator_id, "deleted": True})


# ---------------------------------------------------------------------------
# 自动修复建议端点
# ---------------------------------------------------------------------------


class SuggestFixResponse(BaseModel):
    """修复建议响应。"""

    locator_id: str
    original: dict
    suggestions: list[dict]
    note: str = Field(
        default="本接口仅生成建议，不自动覆盖原定位器。请人工确认后通过 PUT 更新。"
    )


def _build_suggestions(loc: UILocator) -> list[dict]:
    """根据定位器现有信息生成备选修复建议。

    策略（不依赖真实浏览器，纯静态推断）：
    1. 若有 alternative_selectors，将所有备选作为高优先级建议
    2. 根据当前 selector_type 派生其他类型的等价定位器：
       - css → text（若 selector_value 看起来像 .class/#id，生成基于属性的 xpath）
       - text → css（生成 text= 选择器作为兜底）
       - xpath → css（提示用户改为更稳定的 css/test_id）
    3. 始终建议引入 test_id 定位器（data-testid）作为最稳定方案
    """
    suggestions: list[dict] = []
    seen_values: set[str] = set()

    def _add(s_type: str, s_value: str, reason: str) -> None:
        if not s_value or s_value in seen_values:
            return
        seen_values.add(s_value)
        suggestions.append({
            "selector_type": s_type,
            "selector_value": s_value,
            "reason": reason,
        })

    # 1. 已有备选定位器
    alts = _safe_json_loads(loc.alternative_selectors)
    if isinstance(alts, list):
        for alt in alts:
            if isinstance(alt, dict) and alt.get("value"):
                _add(
                    str(alt.get("type", "css")),
                    str(alt["value"]),
                    "来自 alternative_selectors 备选定位器",
                )

    # 2. 基于 selector_type 派生
    sel_type = (loc.selector_type or "css").lower()
    sel_val = loc.selector_value or ""

    if sel_type == "css":
        # .foo → [class*='foo']；#bar → [id='bar']
        if sel_val.startswith(".") and len(sel_val) > 1:
            cls = sel_val[1:]
            _add("xpath", f"//*[contains(@class, '{cls}')]", "CSS 类选择器的 XPath 等价形式")
        elif sel_val.startswith("#") and len(sel_val) > 1:
            eid = sel_val[1:]
            _add("xpath", f"//*[@id='{eid}']", "ID 选择器的 XPath 等价形式")
        _add("css", sel_val, "保留原 CSS 选择器")
    elif sel_type == "xpath":
        _add("css", sel_val, "保留原 XPath（建议改为更稳定的 css/test_id）")
    elif sel_type == "text":
        _add("text", sel_val, "保留文本定位器（脆弱，页面文案变化即失效）")

    # 3. 始终建议 test_id（最稳定）
    if loc.name:
        # 由名称生成一个建议的 data-testid（仅作示例）
        slug = "".join(c if c.isalnum() else "-" for c in loc.name).strip("-").lower()
        if slug:
            _add("test_id", slug, "建议为元素添加 data-testid 属性，使用最稳定的定位方式")

    return suggestions


@router.post("/{locator_id}/suggest-fix", response_model=DataResponse[SuggestFixResponse])
def suggest_fix(
    locator_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成定位器修复建议（不自动覆盖）。

    返回基于现有定位器信息静态推断的备选定位器列表，调用方需人工确认后通过 PUT 更新。
    """
    loc = _get_or_404(db, locator_id)
    ensure_resource_role(db, current_user, loc, "viewer", owner_field=None)
    suggestions = _build_suggestions(loc)
    if not suggestions:
        raise ValidationError("无法为该定位器生成修复建议，请补充 alternative_selectors 或 description")
    response = SuggestFixResponse(
        locator_id=loc.id,
        original=_serialize_locator(loc),
        suggestions=suggestions,
    )
    return DataResponse(data=response)


__all__ = ["router"]
