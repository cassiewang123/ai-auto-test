"""allow null call_history.body

Revision ID: 5f8a4b2c7e3d
Revises: d3f7b9a1c420
Create Date: 2026-09-02 11:00:00

请求体并非必填（GET / 无 body 的 quick_test 均合法），使 call_history.body
与 headers/params/response_body 等同级可选字段保持一致，避免 NOT NULL
约束在无请求体场景下阻断落库。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "5f8a4b2c7e3d"
down_revision: str | None = "d3f7b9a1c420"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("call_history") as batch_op:
        batch_op.alter_column("body", nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("call_history") as batch_op:
        batch_op.alter_column("body", nullable=False)