"""AI 测试设计会话、测试点与用例草稿模型.

对应文档「AI 测试用例生成」：
一次生成会话（快速生成 / 分步生成）持有需求引用、知识库引用、评审维度与
对话消息；分步生成会先产出「待确认测试点」，人工确认后再产出用例草稿，
最后由用户一键写入用例库（TestCase）。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class TestDesignSession(Base):
    """一次 AI 用例生成会话."""

    __tablename__ = "test_design_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    requirement_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("requirements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    knowledge_base_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 生成模式：quick 快速生成 / stepwise 分步生成
    mode: Mapped[str] = mapped_column(String(16), default="quick")
    # 会话状态：clarifying 追问中 / points_ready 测试点待确认 /
    # cases_ready 用例草稿待写入 / imported 已写入用例库
    status: Mapped[str] = mapped_column(String(16), default="clarifying", index=True)
    # 分析引擎：rule / llm
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    # 评审维度权重：{"覆盖完整性": 3, "正确性": 3, ...}
    review_dimensions: Mapped[dict] = mapped_column(JSONText, default=dict)
    # 用户补充描述
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 对话消息：[{"role": "user"|"assistant", "content": "...", "kind": "..."}]
    messages: Mapped[list] = mapped_column(JSONText, default=list)
    # 引用到的知识库分块，便于回溯
    knowledge_refs: Mapped[list] = mapped_column(JSONText, default=list)
    # 写入用例库后记录的用例 ID
    case_ids: Mapped[list] = mapped_column(JSONText, default=list)
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


class GeneratedTestPoint(Base):
    """待确认测试点：先确认范围，再生成用例，降低人工审核成本."""

    __tablename__ = "generated_test_points"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_design_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    order: Mapped[int] = mapped_column(Integer, default=0)
    module: Mapped[str] = mapped_column(String(128), default="通用")
    point: Mapped[str] = mapped_column(Text)
    # 分类：功能 / 异常 / 边界 / 权限 / 性能 / 安全 / 兼容
    category: Mapped[str] = mapped_column(String(16), default="功能")
    priority: Mapped[str] = mapped_column(String(8), default="P1")
    # 用户是否勾选确认生成
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    # 需求追溯：来自哪条功能清单/界面描述
    trace_source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class GeneratedCase(Base):
    """AI 生成的用例草稿（写入用例库前的人工确认态）."""

    __tablename__ = "generated_cases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_design_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    test_point_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("generated_test_points.id", ondelete="SET NULL"),
        nullable=True,
    )
    order: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(256))
    module: Mapped[str] = mapped_column(String(128), default="通用")
    category: Mapped[str] = mapped_column(String(16), default="功能")
    priority: Mapped[str] = mapped_column(String(8), default="P1")
    preconditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list] = mapped_column(JSONText, default=list)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 需求追溯
    trace_source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    # 写入用例库后对应的 TestCase ID
    imported_case_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
