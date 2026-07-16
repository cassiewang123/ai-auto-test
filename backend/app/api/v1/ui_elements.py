"""UI 元素对象库 CRUD API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.ui_element import UiElement
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
# Pydantic Schemas（内联定义）
# ---------------------------------------------------------------------------

class UiElementCreate(BaseModel):
    """创建 UI 元素."""
    name: str
    selector_type: str = "css"  # css/xpath/id/name
    selector_value: str
    page_url: str | None = None
    description: str | None = None
    project_id: str | None = None


class UiElementUpdate(BaseModel):
    """更新 UI 元素（部分更新）."""
    name: str | None = None
    selector_type: str | None = None
    selector_value: str | None = None
    page_url: str | None = None
    description: str | None = None
    project_id: str | None = None


# ---------------------------------------------------------------------------
# 序列化辅助函数
# ---------------------------------------------------------------------------

def _serialize_element(e: UiElement) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "selector_type": e.selector_type,
        "selector_value": e.selector_value,
        "page_url": e.page_url,
        "description": e.description,
        "project_id": e.project_id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD 端点
# ---------------------------------------------------------------------------

@router.get("", response_model=PageResponse[dict])
def list_ui_elements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    name_search: str | None = Query(None, description="按名称模糊搜索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """UI 元素列表分页，支持按 project_id、名称筛选."""
    query = select(UiElement)
    count_query = select(func.count()).select_from(UiElement)
    if project_id is not None:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(
        query, UiElement, current_user, owner_field=None
    )
    count_query = scope_project_resources(
        count_query, UiElement, current_user, owner_field=None
    )

    if project_id is not None:
        query = query.where(UiElement.project_id == project_id)
        count_query = count_query.where(UiElement.project_id == project_id)
    if name_search:
        query = query.where(UiElement.name.like(f"%{name_search}%"))
        count_query = count_query.where(UiElement.name.like(f"%{name_search}%"))

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(UiElement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_element(e) for e in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("", response_model=DataResponse[dict])
def create_ui_element(
    payload: UiElementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建 UI 元素."""
    ensure_project_assignment(db, current_user, payload.project_id, "developer")
    element = UiElement(**payload.model_dump())
    db.add(element)
    db.commit()
    db.refresh(element)
    return DataResponse(data=_serialize_element(element))


@router.get("/{element_id}", response_model=DataResponse[dict])
def get_ui_element(
    element_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个 UI 元素."""
    element = db.get(UiElement, element_id)
    if not element:
        raise NotFoundError("UI 元素", element_id)
    ensure_resource_role(
        db, current_user, element, "viewer", owner_field=None
    )
    return DataResponse(data=_serialize_element(element))


@router.put("/{element_id}", response_model=DataResponse[dict])
def update_ui_element(
    element_id: str,
    payload: UiElementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 UI 元素."""
    element = db.get(UiElement, element_id)
    if not element:
        raise NotFoundError("UI 元素", element_id)
    ensure_resource_role(
        db, current_user, element, "developer", owner_field=None
    )
    update_data = payload.model_dump(exclude_unset=True)
    if (
        "project_id" in update_data
        and update_data["project_id"] != element.project_id
    ):
        ensure_resource_role(
            db, current_user, element, "admin", owner_field=None
        )
        ensure_project_assignment(
            db, current_user, update_data["project_id"], "admin"
        )
    for field, value in update_data.items():
        setattr(element, field, value)
    db.commit()
    db.refresh(element)
    return DataResponse(data=_serialize_element(element))


@router.delete("/{element_id}", response_model=DataResponse[dict])
def delete_ui_element(
    element_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 UI 元素."""
    element = db.get(UiElement, element_id)
    if not element:
        raise NotFoundError("UI 元素", element_id)
    ensure_resource_role(
        db, current_user, element, "admin", owner_field=None
    )
    db.delete(element)
    db.commit()
    return DataResponse(data={"id": element_id, "deleted": True})
