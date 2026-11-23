"""create functional test case tables

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-11-23 15:20:00

AI 用例生成产出的功能测试用例不再写入 API 自动化用例表（test_cases），
改为独立的 functional_test_cases，并新增人工执行记录表。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "functional_test_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("module", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="功能"),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="P1"),
        sa.Column("preconditions", sa.Text(), nullable=True),
        sa.Column("steps", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("trace_source", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("requirement_id", sa.String(length=36), nullable=True),
        sa.Column("design_session_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["requirements.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_functional_test_cases_title", "functional_test_cases", ["title"]
    )
    op.create_index(
        "ix_functional_test_cases_module", "functional_test_cases", ["module"]
    )
    op.create_index(
        "ix_functional_test_cases_priority", "functional_test_cases", ["priority"]
    )
    op.create_index(
        "ix_functional_test_cases_status", "functional_test_cases", ["status"]
    )
    op.create_index(
        "ix_functional_test_cases_requirement_id",
        "functional_test_cases",
        ["requirement_id"],
    )
    op.create_index(
        "ix_functional_test_cases_project_id",
        "functional_test_cases",
        ["project_id"],
    )

    op.create_table(
        "functional_case_executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("actual", sa.Text(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("defect_ref", sa.String(length=128), nullable=True),
        sa.Column("executed_by", sa.String(length=36), nullable=True),
        sa.Column("executed_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("run_label", sa.String(length=64), nullable=True),
        sa.Column("order_no", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["functional_test_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["executed_by"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_functional_case_executions_case_id",
        "functional_case_executions",
        ["case_id"],
    )
    op.create_index(
        "ix_functional_case_executions_result",
        "functional_case_executions",
        ["result"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_functional_case_executions_result",
        table_name="functional_case_executions",
    )
    op.drop_index(
        "ix_functional_case_executions_case_id",
        table_name="functional_case_executions",
    )
    op.drop_table("functional_case_executions")

    for index_name in (
        "ix_functional_test_cases_project_id",
        "ix_functional_test_cases_requirement_id",
        "ix_functional_test_cases_status",
        "ix_functional_test_cases_priority",
        "ix_functional_test_cases_module",
        "ix_functional_test_cases_title",
    ):
        op.drop_index(index_name, table_name="functional_test_cases")
    op.drop_table("functional_test_cases")
