"""全局变量/工作空间变量 CRUD API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models import GlobalVariable
from app.schemas.common import DataResponse, PageResponse
from app.schemas.global_variable import (
    GlobalVariableCreate,
    GlobalVariableResponse,
    GlobalVariableUpdate,
)

router = APIRouter()


def _get_or_404(db: Session, var_id: str) -> GlobalVariable:
    var = db.get(GlobalVariable, var_id)
    if not var:
        raise NotFoundError("全局变量", var_id)
    return var


@router.get("", response_model=PageResponse[GlobalVariableResponse])
def list_variables(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    scope: str | None = Query(None, description="按作用域筛选：global/workspace"),
    project_id: str | None = Query(None, description="按项目筛选（workspace 作用域）"),
    name: str | None = Query(None, description="按名称模糊搜索"),
    db: Session = Depends(get_db),
):
    """变量列表分页，支持按 scope/project_id/name 筛选.

    当 project_id 不为空时，同时返回该项目的 workspace 变量与所有 global 变量。
    """
    query = select(GlobalVariable)
    if scope:
        query = query.where(GlobalVariable.scope == scope)
    if project_id:
        # 限定为该项目的工作空间变量，或全局变量
        query = query.where(
            or_(
                GlobalVariable.project_id == project_id,
                GlobalVariable.scope == "global",
            )
        )
    if name:
        query = query.where(GlobalVariable.name.ilike(f"%{name}%"))

    count_query = select(func.count()).select_from(GlobalVariable)
    if scope:
        count_query = count_query.where(GlobalVariable.scope == scope)
    if project_id:
        count_query = count_query.where(
            or_(
                GlobalVariable.project_id == project_id,
                GlobalVariable.scope == "global",
            )
        )
    if name:
        count_query = count_query.where(GlobalVariable.name.ilike(f"%{name}%"))
    total = db.execute(count_query).scalar_one()

    items = (
        db.execute(
            query.order_by(GlobalVariable.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[GlobalVariableResponse](
        data=items, total=total, page=page, page_size=page_size
    )


@router.get("/{var_id}", response_model=DataResponse[GlobalVariableResponse])
def get_variable(var_id: str, db: Session = Depends(get_db)):
    """获取单个变量."""
    var = _get_or_404(db, var_id)
    return DataResponse[GlobalVariableResponse](data=var)


@router.post("", response_model=DataResponse[GlobalVariableResponse])
def create_variable(payload: GlobalVariableCreate, db: Session = Depends(get_db)):
    """创建变量。workspace 作用域必须指定 project_id."""
    if payload.scope == "workspace" and not payload.project_id:
        raise ValidationError("workspace 作用域的变量必须指定 project_id")
    # 校验 var_type
    if payload.var_type not in ("string", "number", "boolean", "json"):
        raise ValidationError(
            "var_type 必须为 string/number/boolean/json",
            detail={"var_type": payload.var_type},
        )
    var = GlobalVariable(**payload.model_dump())
    db.add(var)
    db.commit()
    db.refresh(var)
    return DataResponse[GlobalVariableResponse](data=var)


@router.put("/{var_id}", response_model=DataResponse[GlobalVariableResponse])
def update_variable(
    var_id: str,
    payload: GlobalVariableUpdate,
    db: Session = Depends(get_db),
):
    """更新变量（部分更新）."""
    var = _get_or_404(db, var_id)
    update_data = payload.model_dump(exclude_unset=True)
    if update_data.get("scope") == "workspace" and not (
        update_data.get("project_id") or var.project_id
    ):
        raise ValidationError("workspace 作用域的变量必须指定 project_id")
    if "var_type" in update_data and update_data["var_type"] not in (
        "string",
        "number",
        "boolean",
        "json",
    ):
        raise ValidationError(
            "var_type 必须为 string/number/boolean/json",
            detail={"var_type": update_data["var_type"]},
        )
    for field, value in update_data.items():
        setattr(var, field, value)
    db.commit()
    db.refresh(var)
    return DataResponse[GlobalVariableResponse](data=var)


@router.delete("/{var_id}", response_model=DataResponse[GlobalVariableResponse])
def delete_variable(var_id: str, db: Session = Depends(get_db)):
    """删除变量."""
    var = _get_or_404(db, var_id)
    data = GlobalVariableResponse.model_validate(var)
    db.delete(var)
    db.commit()
    return DataResponse[GlobalVariableResponse](data=data)
