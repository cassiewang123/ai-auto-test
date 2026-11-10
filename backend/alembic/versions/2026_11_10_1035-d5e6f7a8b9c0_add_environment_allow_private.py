"""add allow_private to environments

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-11-10 10:35:00

按环境放行内网地址，避免为了调试内网接口全局关闭 SSRF 防护。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("environments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "allow_private",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("environments") as batch_op:
        batch_op.drop_column("allow_private")
