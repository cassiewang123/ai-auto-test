"""AI 运营治理 API：调用记录查询、统计、人工反馈."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ai_invocation import AIInvocation
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse, ResponseBase
from app.services.ai_governance import AIGovernanceService
from app.services.auth_service import get_current_user

router = APIRouter()


def _serialize(inv: AIInvocation) -> dict:
    return {
        "id": inv.id,
        "model": inv.model,
        "provider": inv.provider,
        "prompt_version": inv.prompt_version,
        "input_hash": inv.input_hash,
        "token_usage_input": inv.token_usage_input,
        "token_usage_output": inv.token_usage_output,
        "token_usage_total": inv.token_usage_total,
        "latency_ms": inv.latency_ms,
        "cost": inv.cost,
        "output_schema_valid": inv.output_schema_valid,
        "accepted": inv.accepted,
        "edited": inv.edited,
        "rejected": inv.rejected,
        "feedback_comment": inv.feedback_comment,
        "invoked_by": inv.invoked_by,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


@router.get("/invocations", response_model=PageResponse[dict])
def list_invocations(
    model: str | None = Query(None, description="按模型筛选"),
    provider: str | None = Query(None, description="按供应商筛选"),
    start_time: datetime | None = Query(None, description="起始时间 (ISO 8601)"),
    end_time: datetime | None = Query(None, description="结束时间 (ISO 8601)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """分页查询 AI 调用记录."""
    stmt = select(AIInvocation)
    count_stmt = select(func.count()).select_from(AIInvocation)

    if model:
        stmt = stmt.where(AIInvocation.model == model)
        count_stmt = count_stmt.where(AIInvocation.model == model)
    if provider:
        stmt = stmt.where(AIInvocation.provider == provider)
        count_stmt = count_stmt.where(AIInvocation.provider == provider)
    if start_time:
        stmt = stmt.where(AIInvocation.created_at >= start_time)
        count_stmt = count_stmt.where(AIInvocation.created_at >= start_time)
    if end_time:
        stmt = stmt.where(AIInvocation.created_at <= end_time)
        count_stmt = count_stmt.where(AIInvocation.created_at <= end_time)

    total = db.execute(count_stmt).scalar_one()
    items = (
        db.execute(
            stmt.order_by(desc(AIInvocation.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize(i) for i in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=DataResponse[dict])
def get_stats(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    db: Session = Depends(get_db),
):
    """获取 AI 调用统计."""
    service = AIGovernanceService(db)
    stats = service.get_stats(days=days)
    return DataResponse(data=stats)


class FeedbackRequest(BaseModel):
    """人工反馈请求体."""

    accepted: bool | None = Field(default=None, description="采纳")
    edited: bool | None = Field(default=None, description="修改后采纳")
    rejected: bool | None = Field(default=None, description="拒绝")
    comment: str | None = Field(default=None, description="反馈评论")
    rating: int | None = Field(default=None, ge=1, le=5, description="1-5 星评分")


@router.post("/invocations/{invocation_id}/feedback", response_model=ResponseBase)
def submit_feedback(
    invocation_id: str,
    payload: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交对某次 AI 调用的人工反馈."""
    service = AIGovernanceService(db)
    service.record_feedback(
        invocation_id=invocation_id,
        accepted=payload.accepted,
        edited=payload.edited,
        rejected=payload.rejected,
        comment=payload.comment,
        rating=payload.rating,
        created_by=current_user.id,
    )
    return ResponseBase(message="反馈已提交")
