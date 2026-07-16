"""UI 视觉回归 API：基线管理 + 截图对比.

基线截图存储为 base64 字符串，使用 Pillow 的 ImageChops 做像素级对比，
diff_score <= threshold 视为通过，并生成差异高亮图（红色标注差异区域）。
"""
from __future__ import annotations

import base64
import io

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.visual_baseline import VisualBaseline, VisualDiffResult
from app.schemas.common import DataResponse, PageResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class BaselineCreate(BaseModel):
    """创建视觉基线."""
    ui_test_case_id: str
    name: str
    baseline_image: str  # base64 编码（可带 data:image/png;base64, 前缀）
    threshold: float = 0.1
    screenshot_path: str | None = None


class BaselineUpdate(BaseModel):
    """更新视觉基线."""
    name: str | None = None
    baseline_image: str | None = None
    threshold: float | None = None
    screenshot_path: str | None = None


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _strip_data_uri(b64_str: str) -> str:
    """去掉 data:image/...;base64, 前缀，返回纯 base64 字符串."""
    if b64_str and b64_str.startswith("data:"):
        # 格式形如 data:image/png;base64,xxxx
        comma_idx = b64_str.find(",")
        if comma_idx != -1:
            return b64_str[comma_idx + 1:]
    return b64_str


def _serialize_baseline(b: VisualBaseline) -> dict:
    return {
        "id": b.id,
        "ui_test_case_id": b.ui_test_case_id,
        "name": b.name,
        "screenshot_path": b.screenshot_path,
        # baseline_image 较大，列表接口默认不返回，详情接口返回
        "baseline_image": b.baseline_image,
        "threshold": b.threshold,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _serialize_diff(d: VisualDiffResult) -> dict:
    return {
        "id": d.id,
        "ui_test_record_id": d.ui_test_record_id,
        "baseline_id": d.baseline_id,
        "diff_score": d.diff_score,
        "diff_image": d.diff_image,
        "passed": d.passed,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def compare_images(baseline_b64: str, current_b64: str) -> tuple[float, str]:
    """对比两张 base64 图片，返回 (diff_score 0-1, diff_image_base64).

    使用 Pillow 的 ImageChops.difference 计算逐像素差异，
    生成差异可视化图（基线灰度背景 + 红色高亮差异区域）。

    若 Pillow 未安装或图片解码失败，返回 (1.0, "") 表示无法对比。
    """
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return 1.0, ""

    try:
        baseline_b64 = _strip_data_uri(baseline_b64)
        current_b64 = _strip_data_uri(current_b64)
        baseline = Image.open(io.BytesIO(base64.b64decode(baseline_b64))).convert("RGB")
        current = Image.open(io.BytesIO(base64.b64decode(current_b64))).convert("RGB")
    except Exception:
        return 1.0, ""

    # 尺寸对齐：以基线为准
    if baseline.size != current.size:
        current = current.resize(baseline.size)

    # 逐像素差异
    diff = ImageChops.difference(baseline, current)
    # 转灰度并二值化：差异 > 30 视为有差异
    diff_gray = diff.convert("L")
    diff_mask = diff_gray.point(lambda x: 255 if x > 30 else 0)

    # 统计差异像素比例
    histogram = diff_mask.histogram()
    total_pixels = baseline.size[0] * baseline.size[1]
    diff_pixels = histogram[255] if len(histogram) > 255 else 0
    diff_score = diff_pixels / total_pixels if total_pixels else 0.0

    # 生成差异可视化图：基线 + 红色高亮差异区域
    result_img = baseline.convert("RGB").copy()
    red_overlay = Image.new("RGB", baseline.size, (255, 0, 0))
    result_img = Image.composite(red_overlay, result_img, diff_mask)

    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    diff_image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return round(diff_score, 4), diff_image_b64


# ---------------------------------------------------------------------------
# 基线 CRUD 端点
# ---------------------------------------------------------------------------

@router.get("/baselines", response_model=PageResponse[dict])
def list_baselines(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    case_id: str | None = Query(None, description="按 UI 用例筛选"),
    db: Session = Depends(get_db),
):
    """视觉基线列表分页，支持按 case_id 筛选."""
    query = select(VisualBaseline)
    count_query = select(func.count()).select_from(VisualBaseline)

    if case_id is not None:
        query = query.where(VisualBaseline.ui_test_case_id == case_id)
        count_query = count_query.where(VisualBaseline.ui_test_case_id == case_id)

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(VisualBaseline.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize_baseline(b) for b in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("/baselines", response_model=DataResponse[dict])
def create_baseline(payload: BaselineCreate, db: Session = Depends(get_db)):
    """上传/创建视觉基线截图."""
    baseline = VisualBaseline(
        ui_test_case_id=payload.ui_test_case_id,
        name=payload.name,
        baseline_image=_strip_data_uri(payload.baseline_image),
        threshold=payload.threshold,
        screenshot_path=payload.screenshot_path,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return DataResponse(data=_serialize_baseline(baseline))


@router.put("/baselines/{baseline_id}", response_model=DataResponse[dict])
def update_baseline(
    baseline_id: str, payload: BaselineUpdate, db: Session = Depends(get_db)
):
    """更新视觉基线（名称/截图/阈值）."""
    baseline = db.get(VisualBaseline, baseline_id)
    if not baseline:
        raise NotFoundError("视觉基线", baseline_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "baseline_image" and value:
            value = _strip_data_uri(value)
        setattr(baseline, field, value)
    db.commit()
    db.refresh(baseline)
    return DataResponse(data=_serialize_baseline(baseline))


@router.delete("/baselines/{baseline_id}", response_model=DataResponse[dict])
def delete_baseline(baseline_id: str, db: Session = Depends(get_db)):
    """删除视觉基线."""
    baseline = db.get(VisualBaseline, baseline_id)
    if not baseline:
        raise NotFoundError("视觉基线", baseline_id)
    db.delete(baseline)
    db.commit()
    return DataResponse(data={"id": baseline_id, "deleted": True})


# ---------------------------------------------------------------------------
# 差异结果查询
# ---------------------------------------------------------------------------

@router.get("/diffs", response_model=DataResponse[list])
def list_diffs(
    record_id: str | None = Query(None, description="按执行记录筛选"),
    baseline_id: str | None = Query(None, description="按基线筛选"),
    db: Session = Depends(get_db),
):
    """查询视觉回归对比结果，支持按 record_id / baseline_id 筛选."""
    query = select(VisualDiffResult)
    if record_id is not None:
        query = query.where(VisualDiffResult.ui_test_record_id == record_id)
    if baseline_id is not None:
        query = query.where(VisualDiffResult.baseline_id == baseline_id)

    items = db.execute(query.order_by(VisualDiffResult.created_at.desc())).scalars().all()
    data = [_serialize_diff(d) for d in items]
    return DataResponse(data=data)
