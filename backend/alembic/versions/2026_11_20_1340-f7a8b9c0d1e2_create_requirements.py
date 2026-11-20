"""create requirements table

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-11-20 13:40:00

功能测试模块需求管理：存储需求及其关联用例。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("priority", sa.String(8), nullable=False, server_default="P1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
        sa.Column("case_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_requirements_title", "requirements", ["title"])
    op.create_index("ix_requirements_status", "requirements", ["status"])
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_requirements_project_id", table_name="requirements")
    op.drop_index("ix_requirements_status", table_name="requirements")
    op.drop_index("ix_requirements_title", table_name="requirements")
    op.drop_table("requirements")
