"""create api groups table

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-11-24 10:30:00

接口分组原先只由 test_cases.group_path 隐式推导，无法维护空分组或重命名。
本迁移新增 api_groups 表，显式存储分组路径、名称、说明与排序。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_groups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("parent_path", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("project_id", sa.String(length=36), nullable=True),
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
    op.create_index("ix_api_groups_path", "api_groups", ["path"])
    op.create_index("ix_api_groups_project_id", "api_groups", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_api_groups_project_id", table_name="api_groups")
    op.drop_index("ix_api_groups_path", table_name="api_groups")
    op.drop_table("api_groups")
