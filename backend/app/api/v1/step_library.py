"""可复用步骤组 API（Page Object Model 模式）.

提供步骤组的 CRUD、复制、展开预览能力，供 UI 测试用例引用。
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.step_library import StepLibrary
from app.schemas.common import DataResponse, PageResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class StepLibraryCreate(BaseModel):
    """创建可复用步骤组."""

    name: str
    description: str | None = None
    project_id: str | None = None
    steps: list[dict] = []
    tags: list[str] = []


class StepLibraryUpdate(BaseModel):
    """更新可复用步骤组（部分更新）."""

    name: str | None = None
    description: str | None = None
    project_id: str | None = None
    steps: list[dict] | None = None
    tags: list[str] | None = None


# ---------------------------------------------------------------------------
# 序列化辅助函数
# ---------------------------------------------------------------------------

def _serialize_step_group(g: StepLibrary) -> dict:
    """序列化步骤组为字典."""
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "project_id": g.project_id,
        "steps": g.steps or [],
        "step_count": len(g.steps or []),
        "tags": g.tags or [],
        "usage_count": g.usage_count or 0,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


def _get_or_404(db: Session, step_group_id: str) -> StepLibrary:
    """按 id 查询步骤组，不存在则抛出 404."""
    g = db.get(StepLibrary, step_group_id)
    if not g:
        raise NotFoundError("可复用步骤组", step_group_id)
    return g


# ---------------------------------------------------------------------------
# CRUD 端点
# ---------------------------------------------------------------------------

@router.get("", response_model=PageResponse[dict])
def list_step_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    search: str | None = Query(None, description="按名称/描述模糊搜索"),
    db: Session = Depends(get_db),
):
    """步骤组列表分页，支持按 project_id 和名称搜索筛选."""
    query = select(StepLibrary)
    count_query = select(func.count()).select_from(StepLibrary)

    if project_id:
        query = query.where(StepLibrary.project_id == project_id)
        count_query = count_query.where(StepLibrary.project_id == project_id)

    if search:
        kw = f"%{search}%"
        cond = or_(
            StepLibrary.name.ilike(kw),
            StepLibrary.description.ilike(kw),
        )
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = db.execute(count_query).scalar() or 0
    items = (
        db.execute(
            query.order_by(StepLibrary.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return PageResponse(
        data=[_serialize_step_group(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{step_group_id}", response_model=DataResponse[dict])
def get_step_group(step_group_id: str, db: Session = Depends(get_db)):
    """获取步骤组详情."""
    g = _get_or_404(db, step_group_id)
    return DataResponse(data=_serialize_step_group(g))


@router.post("", response_model=DataResponse[dict])
def create_step_group(payload: StepLibraryCreate, db: Session = Depends(get_db)):
    """创建可复用步骤组."""
    g = StepLibrary(
        id=str(_uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        project_id=payload.project_id,
        steps=payload.steps or [],
        tags=payload.tags or [],
        usage_count=0,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return DataResponse(data=_serialize_step_group(g))


@router.put("/{step_group_id}", response_model=DataResponse[dict])
def update_step_group(
    step_group_id: str,
    payload: StepLibraryUpdate,
    db: Session = Depends(get_db),
):
    """更新步骤组（部分更新）."""
    g = _get_or_404(db, step_group_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(g, k, v)
    db.commit()
    db.refresh(g)
    return DataResponse(data=_serialize_step_group(g))


@router.delete("/{step_group_id}", response_model=DataResponse[dict])
def delete_step_group(step_group_id: str, db: Session = Depends(get_db)):
    """删除步骤组."""
    g = _get_or_404(db, step_group_id)
    db.delete(g)
    db.commit()
    return DataResponse(data={"id": step_group_id, "deleted": True})


# ---------------------------------------------------------------------------
# 复制步骤组
# ---------------------------------------------------------------------------

@router.post("/{step_group_id}/duplicate", response_model=DataResponse[dict])
def duplicate_step_group(step_group_id: str, db: Session = Depends(get_db)):
    """复制一个已有步骤组，生成副本（名称后缀 "_副本"）."""
    g = _get_or_404(db, step_group_id)
    new_g = StepLibrary(
        id=str(_uuid.uuid4()),
        name=f"{g.name}_副本",
        description=g.description,
        project_id=g.project_id,
        # 深拷贝步骤与标签，避免引用同一 list 对象
        steps=[dict(s) for s in (g.steps or [])],
        tags=list(g.tags or []),
        usage_count=0,
    )
    db.add(new_g)
    db.commit()
    db.refresh(new_g)
    return DataResponse(data=_serialize_step_group(new_g))


# ---------------------------------------------------------------------------
# 展开步骤组（预览）
# ---------------------------------------------------------------------------

@router.get("/{step_group_id}/expand", response_model=DataResponse[dict])
def expand_step_group(step_group_id: str, db: Session = Depends(get_db)):
    """展开步骤组，返回完整步骤列表，用于预览.

    返回结构：
    {
        "id": "...",
        "name": "登录操作",
        "steps": [ {action, selector, value, ...}, ... ]
    }
    """
    g = _get_or_404(db, step_group_id)
    return DataResponse(
        data={
            "id": g.id,
            "name": g.name,
            "steps": g.steps or [],
        }
    )
