"""知识库（RAG）API：知识库 CRUD、文档上传与索引、试检索.

端点：
    GET    /knowledge-bases                      — 知识库列表
    POST   /knowledge-bases                      — 创建知识库
    GET    /knowledge-bases/{id}                 — 知识库详情
    PUT    /knowledge-bases/{id}                 — 更新知识库
    DELETE /knowledge-bases/{id}                 — 删除知识库
    POST   /knowledge-bases/{id}/documents       — 上传文档（解析 + 建索引）
    GET    /knowledge-bases/{id}/documents       — 文档列表
    DELETE /knowledge-bases/{id}/documents/{did} — 删除文档
    POST   /knowledge-bases/{id}/documents/{did}/reindex — 重建单文档索引
    GET    /knowledge-bases/{id}/documents/{did}/chunks  — 查看分块
    POST   /knowledge-bases/{id}/rebuild-index   — 重建整个知识库索引
    POST   /knowledge-bases/{id}/retrieve        — 试检索
    POST   /knowledge-bases/chunk-preview        — 分块参数预览
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.knowledge_base import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse, ResponseBase
from app.schemas.knowledge_base import (
    ChunkPreviewRequest,
    ChunkPreviewResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    KnowledgeChunkResponse,
    KnowledgeDocumentResponse,
    RetrievalResult,
)
from app.services.auth_service import get_current_user
from app.services.knowledge_base_service import (
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    KnowledgeBaseService,
)
from app.services.rag_text_splitter import split_text
from app.services.requirement_document_parser import (
    DocumentParseError,
    parse_document,
)

router = APIRouter()
_service = KnowledgeBaseService()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _get_or_404(db: Session, knowledge_base_id: str) -> KnowledgeBase:
    item = db.get(KnowledgeBase, knowledge_base_id)
    if not item:
        raise NotFoundError("知识库", knowledge_base_id)
    return item


def _get_document_or_404(
    db: Session, knowledge_base_id: str, document_id: str
) -> KnowledgeDocument:
    document = db.get(KnowledgeDocument, document_id)
    if not document or document.knowledge_base_id != knowledge_base_id:
        raise NotFoundError("知识库文档", document_id)
    return document


def _to_response(db: Session, item: KnowledgeBase) -> KnowledgeBaseResponse:
    stats = _service.document_stats(db, item.id)
    data = KnowledgeBaseResponse.model_validate(item)
    data.document_count = stats["document_count"]
    data.chunk_count = stats["chunk_count"]
    return data


def _document_response(document: KnowledgeDocument) -> KnowledgeDocumentResponse:
    data = KnowledgeDocumentResponse.model_validate(document)
    data.warnings = list(document.warnings or [])
    return data


def _validate_chunk_config(
    strategy: str, chunk_size: int, chunk_overlap: int
) -> None:
    error = _service.validate_chunk_config(strategy, chunk_size, chunk_overlap)
    if error:
        raise ValidationError(error)


# ===========================================================================
# 知识库 CRUD
# ===========================================================================
@router.get("", response_model=PageResponse[KnowledgeBaseResponse])
def list_knowledge_bases(
    project_id: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """知识库列表分页."""
    query = select(KnowledgeBase)
    count_q = select(func.count()).select_from(KnowledgeBase)
    if project_id:
        query = query.where(KnowledgeBase.project_id == project_id)
        count_q = count_q.where(KnowledgeBase.project_id == project_id)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(KnowledgeBase.name.like(pattern))
        count_q = count_q.where(KnowledgeBase.name.like(pattern))

    total = db.execute(count_q).scalar_one()
    items = (
        db.execute(
            query.order_by(KnowledgeBase.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[KnowledgeBaseResponse](
        data=[_to_response(db, item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DataResponse[KnowledgeBaseResponse])
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建知识库."""
    _validate_chunk_config(
        payload.chunk_strategy, payload.chunk_size, payload.chunk_overlap
    )
    item = KnowledgeBase(**payload.model_dump(), created_by=current_user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return DataResponse[KnowledgeBaseResponse](data=_to_response(db, item))


@router.post("/chunk-preview", response_model=DataResponse[ChunkPreviewResponse])
def preview_chunks(payload: ChunkPreviewRequest):
    """分块参数预览：保存前先确认切分效果."""
    _validate_chunk_config(
        payload.chunk_strategy, payload.chunk_size, payload.chunk_overlap
    )
    chunks = split_text(
        payload.text,
        strategy=payload.chunk_strategy,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
    )
    return DataResponse[ChunkPreviewResponse](
        data=ChunkPreviewResponse(
            chunk_count=len(chunks),
            chunks=[
                {
                    "index": chunk.index,
                    "heading": chunk.heading,
                    "char_count": chunk.char_count,
                    "content": chunk.content,
                }
                for chunk in chunks[:50]
            ],
        )
    )


@router.get("/{knowledge_base_id}", response_model=DataResponse[KnowledgeBaseResponse])
def get_knowledge_base(
    knowledge_base_id: str, db: Session = Depends(get_db)
):
    """知识库详情."""
    item = _get_or_404(db, knowledge_base_id)
    return DataResponse[KnowledgeBaseResponse](data=_to_response(db, item))


@router.put("/{knowledge_base_id}", response_model=DataResponse[KnowledgeBaseResponse])
def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
):
    """更新知识库；分块参数变化后需调用重建索引接口."""
    item = _get_or_404(db, knowledge_base_id)
    changes = payload.model_dump(exclude_unset=True)

    strategy = changes.get("chunk_strategy", item.chunk_strategy)
    chunk_size = changes.get("chunk_size", item.chunk_size)
    chunk_overlap = changes.get("chunk_overlap", item.chunk_overlap)
    _validate_chunk_config(strategy, chunk_size, chunk_overlap)

    for field, value in changes.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return DataResponse[KnowledgeBaseResponse](data=_to_response(db, item))


@router.delete("/{knowledge_base_id}", response_model=ResponseBase)
def delete_knowledge_base(
    knowledge_base_id: str, db: Session = Depends(get_db)
):
    """删除知识库（级联删除文档与分块）."""
    item = _get_or_404(db, knowledge_base_id)
    db.delete(item)
    db.commit()
    return ResponseBase()


# ===========================================================================
# 文档
# ===========================================================================
@router.get(
    "/{knowledge_base_id}/documents",
    response_model=PageResponse[KnowledgeDocumentResponse],
)
def list_documents(
    knowledge_base_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """知识库文档列表."""
    _get_or_404(db, knowledge_base_id)
    base = select(KnowledgeDocument).where(
        KnowledgeDocument.knowledge_base_id == knowledge_base_id
    )
    total = db.execute(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
    ).scalar_one()
    items = (
        db.execute(
            base.order_by(KnowledgeDocument.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[KnowledgeDocumentResponse](
        data=[_document_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=DataResponse[KnowledgeDocumentResponse],
)
async def upload_document(
    knowledge_base_id: str,
    file: UploadFile = File(...),
    category: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传文档：解析正文 → 按配置分块 → 建立索引."""
    knowledge_base = _get_or_404(db, knowledge_base_id)

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError("文档超过 20MB 上限")

    try:
        parsed = parse_document(file.filename or "", data)
    except DocumentParseError as exc:
        raise ValidationError(str(exc)) from exc
    except Exception as exc:
        raise ValidationError(f"文档解析失败: {exc}") from exc

    document = KnowledgeDocument(
        knowledge_base_id=knowledge_base.id,
        filename=parsed.filename,
        category=(category or None),
        file_type=parsed.file_type,
        file_size=parsed.file_size,
        content=parsed.content or None,
        status="pending",
        warnings=parsed.warnings,
        created_by=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    _service.build_index(db, document, knowledge_base)
    db.refresh(document)
    return DataResponse[KnowledgeDocumentResponse](
        data=_document_response(document)
    )


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}", response_model=ResponseBase
)
def delete_document(
    knowledge_base_id: str, document_id: str, db: Session = Depends(get_db)
):
    """删除文档及其分块."""
    document = _get_document_or_404(db, knowledge_base_id, document_id)
    db.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
    )
    db.delete(document)
    db.commit()
    return ResponseBase()


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/reindex",
    response_model=DataResponse[KnowledgeDocumentResponse],
)
def reindex_document(
    knowledge_base_id: str, document_id: str, db: Session = Depends(get_db)
):
    """按当前分块参数重建单份文档索引."""
    knowledge_base = _get_or_404(db, knowledge_base_id)
    document = _get_document_or_404(db, knowledge_base_id, document_id)
    _service.build_index(db, document, knowledge_base)
    db.refresh(document)
    return DataResponse[KnowledgeDocumentResponse](
        data=_document_response(document)
    )


@router.get(
    "/{knowledge_base_id}/documents/{document_id}/chunks",
    response_model=PageResponse[KnowledgeChunkResponse],
)
def list_chunks(
    knowledge_base_id: str,
    document_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """查看文档的分块内容."""
    _get_document_or_404(db, knowledge_base_id, document_id)
    total = db.execute(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document_id)
    ).scalar_one()
    items = (
        db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[KnowledgeChunkResponse](
        data=[KnowledgeChunkResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{knowledge_base_id}/rebuild-index", response_model=DataResponse[dict]
)
def rebuild_index(knowledge_base_id: str, db: Session = Depends(get_db)):
    """按当前分块参数重建整个知识库索引."""
    _get_or_404(db, knowledge_base_id)
    result = _service.rebuild_index(db, knowledge_base_id)
    return DataResponse(data=result)


# ===========================================================================
# 检索
# ===========================================================================
@router.post("/{knowledge_base_id}/retrieve", response_model=DataResponse[RetrievalResult])
def retrieve(
    knowledge_base_id: str,
    query: str = Query(..., min_length=1, description="检索内容"),
    top_k: int = Query(DEFAULT_TOP_K, ge=1, le=20),
    min_score: float = Query(DEFAULT_MIN_SCORE, ge=0, le=1),
    db: Session = Depends(get_db),
):
    """试检索：验证分块粒度与检索效果."""
    _get_or_404(db, knowledge_base_id)
    result = _service.retrieve(
        db, knowledge_base_id, query, top_k=top_k, min_score=min_score
    )
    return DataResponse[RetrievalResult](
        data=RetrievalResult(
            hits=result["hits"],
            query_tokens=result["query_tokens"],
            hit_count=result["hit_count"],
            top_score=result["top_score"],
        )
    )
