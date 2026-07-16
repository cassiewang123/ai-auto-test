"""数据驱动测试数据集管理 API.

端点：
    GET    /test-data                 — 列表（可按 test_case_id 筛选）
    POST   /test-data                 — 创建数据集
    POST   /test-data/execute         — 数据驱动执行
    GET    /test-data/{data_id}       — 详情
    PUT    /test-data/{data_id}       — 更新
    DELETE /test-data/{data_id}       — 删除
    POST   /test-data/{data_id}/preview — 预览解析结果
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.environment import Environment
from app.models.test_case import TestCase
from app.models.test_data_set import TestDataSet
from app.schemas.common import DataResponse, PageResponse
from app.schemas.test_data import (
    DataSetCreate,
    DataSetPreviewResponse,
    DataSetResponse,
    DataSetUpdate,
    DataDrivenExecutionRequest,
    DataDrivenExecutionResult,
)
from app.services.data_driven_service import (
    execute_data_driven,
    extract_variables,
    parse_csv,
    parse_json,
)

router = APIRouter()


def _get_or_404(db: Session, data_id: str) -> TestDataSet:
    ds = db.get(TestDataSet, data_id)
    if not ds:
        raise NotFoundError("数据集", data_id)
    return ds


def _parse_data(format: str, data: str) -> list[dict]:
    """根据格式解析原始数据，返回字典列表."""
    if format == "csv":
        return parse_csv(data)
    if format == "json":
        return parse_json(data)
    raise ValidationError(f"不支持的格式: {format}")


# ---------- 列表 & 创建（固定路径，必须在 /{data_id} 之前） ----------

@router.get("", response_model=PageResponse[DataSetResponse])
def list_data_sets(
    test_case_id: str | None = Query(None, description="按测试用例筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """数据集列表分页，支持按 test_case_id 筛选."""
    query = select(TestDataSet)
    if test_case_id:
        query = query.where(TestDataSet.test_case_id == test_case_id)

    count_query = select(func.count()).select_from(TestDataSet)
    if test_case_id:
        count_query = count_query.where(
            TestDataSet.test_case_id == test_case_id
        )
    total = db.execute(count_query).scalar_one()

    items = (
        db.execute(
            query.order_by(TestDataSet.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[DataSetResponse](
        data=items, total=total, page=page, page_size=page_size
    )


@router.post("", response_model=DataResponse[DataSetResponse])
def create_data_set(payload: DataSetCreate, db: Session = Depends(get_db)):
    """创建数据集，自动解析变量名列表."""
    case = db.get(TestCase, payload.test_case_id)
    if not case:
        raise NotFoundError("测试用例", payload.test_case_id)

    rows = _parse_data(payload.format, payload.data)
    variables = extract_variables(rows)

    ds = TestDataSet(
        name=payload.name,
        description=payload.description,
        format=payload.format,
        data=payload.data,
        variables=variables,
        test_case_id=payload.test_case_id,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return DataResponse[DataSetResponse](data=ds)


# ---------- 数据驱动执行（固定路径，必须在 /{data_id} 之前） ----------

@router.post("/execute", response_model=DataResponse[DataDrivenExecutionResult])
def execute_data_driven_endpoint(
    req: DataDrivenExecutionRequest, db: Session = Depends(get_db)
):
    """数据驱动执行：遍历数据集每行数据，替换变量后执行用例."""
    case = db.get(TestCase, req.test_case_id)
    if not case:
        raise NotFoundError("测试用例", req.test_case_id)

    # 获取数据行
    if req.data_set_id:
        ds = _get_or_404(db, req.data_set_id)
        data_rows = _parse_data(ds.format, ds.data)
    else:
        data_rows = []

    # 获取环境（优先使用请求参数，其次用例配置的环境）
    environment = None
    env_id = req.environment_id or case.environment_id
    if env_id:
        environment = db.get(Environment, env_id)

    results = execute_data_driven(case, data_rows, environment)
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] != "passed")

    return DataResponse[DataDrivenExecutionResult](
        data=DataDrivenExecutionResult(
            total=len(results),
            passed=passed,
            failed=failed,
            results=results,
        )
    )


# ---------- 单个数据集操作（含路径参数 /{data_id}） ----------

@router.get("/{data_id}", response_model=DataResponse[DataSetResponse])
def get_data_set(data_id: str, db: Session = Depends(get_db)):
    """获取数据集详情."""
    ds = _get_or_404(db, data_id)
    return DataResponse[DataSetResponse](data=ds)


@router.put("/{data_id}", response_model=DataResponse[DataSetResponse])
def update_data_set(
    data_id: str,
    payload: DataSetUpdate,
    db: Session = Depends(get_db),
):
    """更新数据集（部分更新）。data 或 format 变更时自动重新解析变量."""
    ds = _get_or_404(db, data_id)
    update_data = payload.model_dump(exclude_unset=True)

    # 如果 data 或 format 变更，重新解析变量
    if "data" in update_data or "format" in update_data:
        fmt = update_data.get("format", ds.format)
        raw = update_data.get("data", ds.data)
        rows = _parse_data(fmt, raw)
        ds.variables = extract_variables(rows)

    for field, value in update_data.items():
        setattr(ds, field, value)

    db.commit()
    db.refresh(ds)
    return DataResponse[DataSetResponse](data=ds)


@router.delete("/{data_id}", response_model=DataResponse[dict])
def delete_data_set(data_id: str, db: Session = Depends(get_db)):
    """删除数据集."""
    ds = _get_or_404(db, data_id)
    db.delete(ds)
    db.commit()
    return DataResponse(data={"deleted": True, "id": data_id})


@router.post("/{data_id}/preview", response_model=DataResponse[DataSetPreviewResponse])
def preview_data_set(data_id: str, db: Session = Depends(get_db)):
    """预览数据集解析结果（变量名 + 前 100 行数据）."""
    ds = _get_or_404(db, data_id)
    rows = _parse_data(ds.format, ds.data)
    preview_rows = rows[:100]
    return DataResponse[DataSetPreviewResponse](
        data=DataSetPreviewResponse(
            variables=ds.variables or extract_variables(rows),
            rows=preview_rows,
        )
    )
