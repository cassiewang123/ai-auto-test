"""add execution job link to defect tickets

Revision ID: a1b2c3d4e5f6
Revises: 5f8a4b2c7e3d
Create Date: 2026-09-10 10:00:00

失败/超时任务自动生成缺陷草稿时，需要记录来源 ExecutionJob 用于展示与去重。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "5f8a4b2c7e3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("defect_tickets") as batch_op:
        batch_op.add_column(
            sa.Column(
                "execution_job_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_defect_tickets_execution_job_id",
            "execution_jobs",
            ["execution_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        op.f("ix_defect_tickets_execution_job_id"),
        "defect_tickets",
        ["execution_job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_defect_tickets_execution_job_id"),
        table_name="defect_tickets",
    )
    with op.batch_alter_table("defect_tickets") as batch_op:
        batch_op.drop_constraint(
            "fk_defect_tickets_execution_job_id",
            type_="foreignkey",
        )
        batch_op.drop_column("execution_job_id")
