"""create knowledge base, requirement document and ai test design tables

Revision ID: b1c2d3e4f5a6
Revises: f7a8b9c0d1e2
Create Date: 2026-11-20 15:00:00

落地三块能力：
1. 需求文档与 AI 结构化分析（requirement_documents / requirement_analyses）；
2. 知识库 RAG（knowledge_bases / knowledge_documents / knowledge_chunks /
   knowledge_retrieval_logs）；
3. AI 测试用例生成（test_design_sessions / generated_test_points /
   generated_cases）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 需求文档
    # ------------------------------------------------------------------
    op.create_table(
        "requirement_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=16), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("warnings", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_requirement_documents_requirement_id",
        "requirement_documents",
        ["requirement_id"],
    )

    # ------------------------------------------------------------------
    # 需求分析结果
    # ------------------------------------------------------------------
    op.create_table(
        "requirement_analyses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("engine", sa.String(length=16), nullable=False, server_default="rule"),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=True),
        sa.Column("function_items", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("ui_descriptions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("clarifications", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("markdown", sa.Text(), nullable=True),
        sa.Column("messages", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_requirement_analyses_requirement_id",
        "requirement_analyses",
        ["requirement_id"],
    )

    # ------------------------------------------------------------------
    # 知识库
    # ------------------------------------------------------------------
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column(
            "chunk_strategy",
            sa.String(length=32),
            nullable=False,
            server_default="fixed_window",
        ),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="400"),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_knowledge_bases_name", "knowledge_bases", ["name"])
    op.create_index(
        "ix_knowledge_bases_project_id", "knowledge_bases", ["project_id"]
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("file_type", sa.String(length=16), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_knowledge_documents_knowledge_base_id",
        "knowledge_documents",
        ["knowledge_base_id"],
    )
    op.create_index(
        "ix_knowledge_documents_status", "knowledge_documents", ["status"]
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("keywords", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("heading", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_knowledge_base_id",
        "knowledge_chunks",
        ["knowledge_base_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"]
    )

    op.create_table(
        "knowledge_retrieval_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("hits", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_knowledge_retrieval_logs_knowledge_base_id",
        "knowledge_retrieval_logs",
        ["knowledge_base_id"],
    )

    # ------------------------------------------------------------------
    # AI 测试用例生成
    # ------------------------------------------------------------------
    op.create_table(
        "test_design_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("requirement_id", sa.String(length=36), nullable=True),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="quick"),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="clarifying"
        ),
        sa.Column("engine", sa.String(length=16), nullable=False, server_default="rule"),
        sa.Column("review_dimensions", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("messages", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("knowledge_refs", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("case_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["requirements.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_test_design_sessions_project_id",
        "test_design_sessions",
        ["project_id"],
    )
    op.create_index(
        "ix_test_design_sessions_requirement_id",
        "test_design_sessions",
        ["requirement_id"],
    )
    op.create_index(
        "ix_test_design_sessions_status", "test_design_sessions", ["status"]
    )

    op.create_table(
        "generated_test_points",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("module", sa.String(length=128), nullable=False, server_default="通用"),
        sa.Column("point", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="功能"),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="P1"),
        sa.Column(
            "selected", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("trace_source", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["test_design_sessions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_generated_test_points_session_id",
        "generated_test_points",
        ["session_id"],
    )

    op.create_table(
        "generated_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("test_point_id", sa.String(length=36), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("module", sa.String(length=128), nullable=False, server_default="通用"),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="功能"),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="P1"),
        sa.Column("preconditions", sa.Text(), nullable=True),
        sa.Column("steps", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("trace_source", sa.String(length=256), nullable=True),
        sa.Column(
            "selected", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("imported_case_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["test_design_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_point_id"],
            ["generated_test_points.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_generated_cases_session_id", "generated_cases", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_generated_cases_session_id", table_name="generated_cases")
    op.drop_table("generated_cases")
    op.drop_index(
        "ix_generated_test_points_session_id",
        table_name="generated_test_points",
    )
    op.drop_table("generated_test_points")
    for index_name in (
        "ix_test_design_sessions_status",
        "ix_test_design_sessions_requirement_id",
        "ix_test_design_sessions_project_id",
    ):
        op.drop_index(index_name, table_name="test_design_sessions")
    op.drop_table("test_design_sessions")

    op.drop_index(
        "ix_knowledge_retrieval_logs_knowledge_base_id",
        table_name="knowledge_retrieval_logs",
    )
    op.drop_table("knowledge_retrieval_logs")
    for index_name in (
        "ix_knowledge_chunks_document_id",
        "ix_knowledge_chunks_knowledge_base_id",
    ):
        op.drop_index(index_name, table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    for index_name in (
        "ix_knowledge_documents_status",
        "ix_knowledge_documents_knowledge_base_id",
    ):
        op.drop_index(index_name, table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    for index_name in (
        "ix_knowledge_bases_project_id",
        "ix_knowledge_bases_name",
    ):
        op.drop_index(index_name, table_name="knowledge_bases")
    op.drop_table("knowledge_bases")

    op.drop_index(
        "ix_requirement_analyses_requirement_id",
        table_name="requirement_analyses",
    )
    op.drop_table("requirement_analyses")
    op.drop_index(
        "ix_requirement_documents_requirement_id",
        table_name="requirement_documents",
    )
    op.drop_table("requirement_documents")
