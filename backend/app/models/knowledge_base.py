"""知识库（RAG 检索增强生成）模型.

文档中的「知识库管理」：统一管理项目相关的技术/业务文档，为 AI 分析与
用例生成提供上下文。文档被解析为纯文本后按可配置粒度切分为分块，并
建立关键词索引，供检索时按相关性召回。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText

# 分块策略：固定窗口 / 按段落 / 按标题
CHUNK_STRATEGIES = ("fixed_window", "paragraph", "heading")


class KnowledgeBase(Base):
    """一个知识库，聚合某项目/主题下的多份文档."""

    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 分块配置：{"strategy": "fixed_window", "chunk_size": 400, "chunk_overlap": 80}
    chunk_strategy: Mapped[str] = mapped_column(
        String(32), default="fixed_window"
    )
    chunk_size: Mapped[int] = mapped_column(Integer, default=400)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=80)
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class KnowledgeDocument(Base):
    """知识库中的一份文档及其解析结果."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512))
    # 文档分类：设计文档/接口文档/业务说明等，缺省「未分类」
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_type: Mapped[str] = mapped_column(String(16), default="txt")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    # 解析出的纯文本
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 索引状态：pending / indexed / failed
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    # 解析告警（例如图片未做 OCR）
    warnings: Mapped[list] = mapped_column(JSONText, default=list)
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class KnowledgeChunk(Base):
    """文档分块，检索的最小单元."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
    )
    # 分块在文档中的序号，从 0 开始
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # 归一化关键词，用于检索打分；保留关键词数组避免向量依赖
    keywords: Mapped[list] = mapped_column(JSONText, default=list)
    # 分块所属标题（按标题切分时填充）
    heading: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class RetrievalLog(Base):
    """知识库检索记录，便于回溯 AI 分析引用了哪些分块."""

    __tablename__ = "knowledge_retrieval_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
    )
    query: Mapped[str] = mapped_column(Text)
    # 召回结果：[{"chunk_id":..., "document_id":..., "score":...}]
    hits: Mapped[list] = mapped_column(JSONText, default=list)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    top_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
