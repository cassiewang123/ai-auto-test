"""知识库 RAG 服务：文档索引、检索与上下文注入.

对应文档「二、知识库管理」：
1. 文档上传后解析为文本，按知识库配置的分块参数切分成多个文本块；
2. 为每个分块建立关键词索引（无向量依赖，离线可用）；
3. 生成用例时按当前需求检索最相关的分块，而不是把整个项目的技术文档
   全部交给模型；
4. 支持「试检索」验证检索效果，以及「重新建立索引」。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.knowledge_base import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievalLog,
)
from app.services.rag_text_splitter import (
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    extract_keywords,
    score_chunk,
    split_text,
    tokenize_query,
)

# 检索默认返回条数；过少上下文不足，过多引入噪声
DEFAULT_TOP_K = 5
MAX_TOP_K = 20
# 低于该相关度的分块不注入，避免无关噪声
DEFAULT_MIN_SCORE = 0.05
# 单次注入 Prompt 的总字符上限，防止超出模型上下文
MAX_CONTEXT_CHARS = 6000


class KnowledgeBaseService:
    """知识库文档索引与检索."""

    # ------------------------------------------------------------------
    # 索引
    # ------------------------------------------------------------------
    def build_index(
        self, db: Session, document: KnowledgeDocument, knowledge_base: KnowledgeBase
    ) -> int:
        """（重新）建立某文档的分块索引，返回分块数量."""
        db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document.id
            )
        )

        text = (document.content or "").strip()
        if not text:
            document.status = "failed"
            document.error_message = "文档无可用正文，无法建立索引"
            document.chunk_count = 0
            db.commit()
            return 0

        chunks = split_text(
            text,
            strategy=knowledge_base.chunk_strategy,
            chunk_size=knowledge_base.chunk_size,
            chunk_overlap=knowledge_base.chunk_overlap,
        )
        for chunk in chunks:
            db.add(
                KnowledgeChunk(
                    knowledge_base_id=knowledge_base.id,
                    document_id=document.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    char_count=chunk.char_count,
                    keywords=extract_keywords(chunk.content),
                    heading=chunk.heading,
                )
            )

        document.chunk_count = len(chunks)
        document.status = "indexed" if chunks else "failed"
        document.error_message = None if chunks else "未切分出任何文本块"
        db.commit()
        return len(chunks)

    def rebuild_index(self, db: Session, knowledge_base_id: str) -> dict[str, Any]:
        """重建整个知识库的索引（分块参数调整后使用）."""
        knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
        if knowledge_base is None:
            raise ValueError("知识库不存在")

        documents = (
            db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.knowledge_base_id == knowledge_base_id
                )
            )
            .scalars()
            .all()
        )
        total_chunks = 0
        failed = 0
        for document in documents:
            count = self.build_index(db, document, knowledge_base)
            total_chunks += count
            if count == 0:
                failed += 1
        return {
            "document_count": len(documents),
            "chunk_count": total_chunks,
            "failed_count": failed,
        }

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def retrieve(
        self,
        db: Session,
        knowledge_base_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        log: bool = True,
    ) -> dict[str, Any]:
        """在知识库中检索与 query 相关的分块."""
        top_k = max(1, min(MAX_TOP_K, int(top_k)))
        query_tokens = tokenize_query(query)
        if not query_tokens:
            return {"hits": [], "query_tokens": [], "hit_count": 0, "top_score": 0.0}

        rows = db.execute(
            select(KnowledgeChunk, KnowledgeDocument.filename)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .where(KnowledgeChunk.knowledge_base_id == knowledge_base_id)
        ).all()

        scored: list[dict[str, Any]] = []
        for chunk, filename in rows:
            score = score_chunk(query_tokens, chunk.keywords or [], chunk.content)
            if score < min_score:
                continue
            scored.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "document_name": filename,
                    "chunk_index": chunk.chunk_index,
                    "heading": chunk.heading,
                    "content": chunk.content,
                    "score": round(score, 4),
                }
            )

        scored.sort(key=lambda item: (-item["score"], item["chunk_index"]))
        hits = scored[:top_k]
        result = {
            "hits": hits,
            "query_tokens": query_tokens,
            "hit_count": len(hits),
            "top_score": hits[0]["score"] if hits else 0.0,
        }

        if log:
            db.add(
                RetrievalLog(
                    knowledge_base_id=knowledge_base_id,
                    query=query[:2000],
                    hits=[
                        {
                            "chunk_id": hit["chunk_id"],
                            "document_id": hit["document_id"],
                            "score": hit["score"],
                        }
                        for hit in hits
                    ],
                    hit_count=len(hits),
                    top_score=result["top_score"],
                )
            )
            db.commit()
        return result

    def retrieve_for_prompt(
        self,
        db: Session,
        knowledge_base_id: str | None,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> tuple[str, list[dict[str, Any]]]:
        """检索并拼装成可注入 Prompt 的上下文文本.

        返回 ``(context_text, hits)``。没有知识库、没有命中或检索失败时
        返回空上下文，调用方按「无参考知识」继续生成。
        """
        if not knowledge_base_id or not (query or "").strip():
            return "", []

        try:
            result = self.retrieve(
                db, knowledge_base_id, query, top_k=top_k, log=False
            )
        except Exception:
            # 检索失败不应阻断生成主流程
            return "", []

        hits = result["hits"]
        if not hits:
            return "", []

        sections: list[str] = ["## 参考知识（知识库检索结果）"]
        used = 0
        kept: list[dict[str, Any]] = []
        for hit in hits:
            block = (
                f"### 来源：{hit['document_name']}"
                f"（分块 {hit['chunk_index']}）\n{hit['content']}"
            )
            if used + len(block) > MAX_CONTEXT_CHARS:
                break
            sections.append(block)
            used += len(block)
            kept.append(hit)

        if not kept:
            return "", []
        return "\n\n".join(sections), kept

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def document_stats(self, db: Session, knowledge_base_id: str) -> dict[str, int]:
        """知识库文档与分块统计."""
        doc_total = db.execute(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
        ).scalar_one()
        chunk_total = db.execute(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.knowledge_base_id == knowledge_base_id)
        ).scalar_one()
        failed = db.execute(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(
                KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.status == "failed",
            )
        ).scalar_one()
        return {
            "document_count": int(doc_total),
            "chunk_count": int(chunk_total),
            "failed_count": int(failed),
        }

    # ------------------------------------------------------------------
    # 参数校验
    # ------------------------------------------------------------------
    @staticmethod
    def validate_chunk_config(
        strategy: str, chunk_size: int, chunk_overlap: int
    ) -> str | None:
        """校验分块参数，返回错误信息（合法时返回 None）."""
        allowed = {"fixed_window", "paragraph", "heading"}
        if strategy not in allowed:
            return f"不支持的分块方式: {strategy}"
        if not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE:
            return (
                f"分块大小需在 {MIN_CHUNK_SIZE}-{MAX_CHUNK_SIZE} 字符之间"
                f"（文档建议 400-1500）"
            )
        if chunk_overlap < 0:
            return "分块重叠不能为负数"
        if chunk_overlap >= chunk_size:
            return "分块重叠必须小于分块大小"
        return None
