"""知识库（RAG）请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseBase(BaseModel):
    """知识库基础字段."""

    name: str = Field(..., min_length=1, max_length=128, description="知识库名称")
    description: str | None = Field(default=None, description="用途说明")
    project_id: str | None = Field(default=None, max_length=36)
    chunk_strategy: str = Field(
        default="fixed_window",
        description="分块方式: fixed_window 固定窗口 / paragraph 按段落 / heading 按标题",
    )
    chunk_size: int = Field(default=400, ge=100, le=4000, description="分块大小")
    chunk_overlap: int = Field(default=80, ge=0, le=4000, description="分块重叠")


class KnowledgeBaseCreate(KnowledgeBaseBase):
    """创建知识库."""


class KnowledgeBaseUpdate(BaseModel):
    """更新知识库（分块参数变更后需重建索引）."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    project_id: str | None = None
    chunk_strategy: str | None = None
    chunk_size: int | None = Field(default=None, ge=100, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=4000)


class KnowledgeBaseResponse(KnowledgeBaseBase):
    """知识库响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    document_count: int = 0
    chunk_count: int = 0


class KnowledgeDocumentResponse(BaseModel):
    """知识库文档响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_base_id: str
    filename: str
    category: str | None = None
    file_type: str
    file_size: int = 0
    status: str = "pending"
    error_message: str | None = None
    chunk_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class KnowledgeChunkResponse(BaseModel):
    """知识库分块响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chunk_index: int
    content: str
    char_count: int = 0
    heading: str | None = None
    keywords: list[str] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    """一条检索命中."""

    chunk_id: str
    document_id: str
    document_name: str
    chunk_index: int
    heading: str | None = None
    content: str
    score: float


class RetrievalResult(BaseModel):
    """检索结果."""

    hits: list[RetrievalHit] = Field(default_factory=list)
    query_tokens: list[str] = Field(default_factory=list)
    hit_count: int = 0
    top_score: float = 0.0


class ChunkPreviewRequest(BaseModel):
    """分块预览请求：调整参数后先看切分效果再保存."""

    text: str = Field(..., min_length=1, description="待切分文本")
    chunk_strategy: str = "fixed_window"
    chunk_size: int = Field(default=400, ge=100, le=4000)
    chunk_overlap: int = Field(default=80, ge=0, le=4000)


class ChunkPreviewResponse(BaseModel):
    """分块预览响应."""

    chunk_count: int = 0
    chunks: list[dict[str, Any]] = Field(default_factory=list)
