"""create server saved requests table

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-11-03 16:20:00

服务器连接工具需要保存调用的接口，便于重复执行。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.database_types import JSONText

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "server_saved_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("url", sa.String(length=4096), nullable=False),
        sa.Column("params", JSONText(), nullable=True),
        sa.Column("headers", JSONText(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_server_saved_requests_created_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_server_saved_requests_created_by"),
        "server_saved_requests",
        ["created_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_server_saved_requests_created_by"),
        table_name="server_saved_requests",
    )
    op.drop_table("server_saved_requests")
