"""create api case records table

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-11-24 16:40:00

新增「用例管理」所需的接口用例库：保存由接口用例生成结果导入的接口测试
用例（方法/URL/参数/请求体/断言），支持列表筛选与 Excel 导出。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_case_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False, server_default="GET"),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("headers", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("params", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("assertions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "case_type", sa.String(length=16), nullable=False, server_default="normal"
        ),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="P1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="ai"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("interface_name", sa.String(length=256), nullable=True),
        sa.Column("group_path", sa.String(length=256), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_api_case_records_title", "api_case_records", ["title"])
    op.create_index("ix_api_case_records_case_type", "api_case_records", ["case_type"])
    op.create_index("ix_api_case_records_priority", "api_case_records", ["priority"])
    op.create_index("ix_api_case_records_status", "api_case_records", ["status"])
    op.create_index("ix_api_case_records_group_path", "api_case_records", ["group_path"])
    op.create_index("ix_api_case_records_project_id", "api_case_records", ["project_id"])


def downgrade() -> None:
    for index_name in (
        "ix_api_case_records_project_id",
        "ix_api_case_records_group_path",
        "ix_api_case_records_status",
        "ix_api_case_records_priority",
        "ix_api_case_records_case_type",
        "ix_api_case_records_title",
    ):
        op.drop_index(index_name, table_name="api_case_records")
    op.drop_table("api_case_records")
