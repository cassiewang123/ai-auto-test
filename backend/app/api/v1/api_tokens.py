"""API Token 管理 API：创建、列表、吊销.

端点：
    GET    /api-tokens          — 列表（脱敏，仅返回 token_prefix）
    POST   /api-tokens          — 创建（返回明文 token 仅此一次）
    DELETE /api-tokens/{id}     — 吊销/删除

SEC-03 迁移说明：token 字段已改为 HMAC-SHA256 哈希存储（token_hash），
列表/详情仅返回 token_prefix（前 8 位）用于识别，不返回明文 token。
创建时返回完整明文 token 并提示用户妥善保存，此后不再显示。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.schemas.ci_cd import (
    ApiTokenCreate,
    ApiTokenCreateResponse,
    ApiTokenResponse,
)
from app.schemas.common import DataResponse, ResponseBase
from app.services.ci_cd_service import create_token, mask_token, revoke_token

router = APIRouter()


def _to_response(tok) -> ApiTokenResponse:
    """将 ApiToken 模型转为脱敏响应（不含明文 token，仅返回 token_prefix）."""
    return ApiTokenResponse(
        id=tok.id,
        name=tok.name,
        token_prefix=tok.token_prefix,
        token_masked=tok.token_prefix,
        scopes=list(tok.scopes or []),
        is_active=tok.is_active,
        expires_at=tok.expires_at,
        last_used_at=tok.last_used_at,
        created_at=tok.created_at,
    )


@router.get("", response_model=DataResponse[list[ApiTokenResponse]])
def list_tokens(db: Session = Depends(get_db)):
    """列出全部 API Token（仅返回脱敏的 token 前缀，不返回明文）."""
    from app.models.api_token import ApiToken

    tokens = (
        db.query(ApiToken).order_by(ApiToken.created_at.desc()).all()
    )
    return DataResponse(data=[_to_response(t) for t in tokens])


@router.post("", response_model=DataResponse[ApiTokenCreateResponse])
def create_api_token(payload: ApiTokenCreate, db: Session = Depends(get_db)):
    """创建 API Token，明文 token 仅在本次响应中返回.

    请妥善保存返回的明文 token，此后将不再显示。
    数据库中仅存储 HMAC-SHA256 哈希值，无法反查明文。
    """
    record, plaintext = create_token(
        db,
        name=payload.name,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        user_id=payload.user_id,
    )
    resp = ApiTokenCreateResponse(
        id=record.id,
        name=record.name,
        token=plaintext,
        token_prefix=record.token_prefix,
        token_masked=mask_token(plaintext),
        scopes=list(record.scopes or []),
        is_active=record.is_active,
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
    )
    return DataResponse(data=resp, message="创建成功，请妥善保存明文 token，此后不再显示")


@router.delete("/{token_id}", response_model=ResponseBase)
def delete_api_token(token_id: str, db: Session = Depends(get_db)):
    """吊销（删除）API Token."""
    revoke_token(db, token_id)
    return ResponseBase()
