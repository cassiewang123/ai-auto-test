"""需求文档与 AI 结构化的分析结果模型.

对应文档「需求管理 → 需求分析」：
需求可携带多份原始文档（PDF / Word / Markdown / 纯文本），系统解析为正文后
由大模型（未启用时由规则引擎兜底）结构化输出三部分：功能清单、界面描述、
待澄清项。分析结果单独成表，便于保留多次重新分析的历史。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class RequirementDocument(Base):
    """需求附件：上传的原始需求文档及其解析出的文本."""

    __tablename__ = "requirement_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    requirement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(16), default="txt")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    # 解析出的纯文本内容
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 解析告警，例如 PDF 为扫描件、需人工补录
    warnings: Mapped[list] = mapped_column(JSONText, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class RequirementAnalysis(Base):
    """一次需求分析的完整结果（功能清单 / 界面描述 / 待澄清项）."""

    __tablename__ = "requirement_analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    requirement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        index=True,
    )
    # 分析引擎：rule 规则兜底 / llm 大模型
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    # 是否引用了知识库（记录知识库 ID，便于回溯）
    knowledge_base_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    # 功能清单：[{"module": "登录与注册", "points": ["...", "..."]}]
    function_items: Mapped[list] = mapped_column(JSONText, default=list)
    # 界面描述：[{"page": "登录页", "description": "..."}]
    ui_descriptions: Mapped[list] = mapped_column(JSONText, default=list)
    # 待澄清项：[{"question": "...", "reason": "..."}]
    clarifications: Mapped[list] = mapped_column(JSONText, default=list)
    # 由以上三部分渲染的 Markdown，可直接导出
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 右侧对话窗口的消息：[{"role": "user"|"assistant", "content": "..."}]
    messages: Mapped[list] = mapped_column(JSONText, default=list)
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
