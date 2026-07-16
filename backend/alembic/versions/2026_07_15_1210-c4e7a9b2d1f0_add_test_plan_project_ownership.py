"""add test plan project ownership

Revision ID: c4e7a9b2d1f0
Revises: 5fbab72fd965
Create Date: 2026-07-15 12:10:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e7a9b2d1f0"
down_revision: str | None = "5fbab72fd965"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("test_plans") as batch_op:
        batch_op.add_column(
            sa.Column("project_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("created_by", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_test_plans_project",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_test_plans_creator",
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_test_plans_project_id",
            ["project_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_test_plans_created_by",
            ["created_by"],
            unique=False,
        )

    # Backfill only non-empty plans whose every item resolves to a scoped case
    # and whose cases all belong to one project. Empty, mixed-project, unscoped,
    # and orphaned plans remain unscoped.
    op.execute(
        sa.text(
            """
            UPDATE test_plans
            SET project_id = (
                SELECT MIN(tc.project_id)
                FROM test_plan_items tpi
                JOIN test_cases tc ON tc.id = tpi.test_case_id
                WHERE tpi.plan_id = test_plans.id
                  AND tc.project_id IS NOT NULL
            )
            WHERE project_id IS NULL
              AND (
                  SELECT COUNT(*)
                  FROM test_plan_items tpi
                  WHERE tpi.plan_id = test_plans.id
              ) > 0
              AND (
                  SELECT COUNT(*)
                  FROM test_plan_items tpi
                  LEFT JOIN test_cases tc ON tc.id = tpi.test_case_id
                  WHERE tpi.plan_id = test_plans.id
                    AND tc.project_id IS NULL
              ) = 0
              AND (
                  SELECT COUNT(DISTINCT tc.project_id)
                  FROM test_plan_items tpi
                  JOIN test_cases tc ON tc.id = tpi.test_case_id
                  WHERE tpi.plan_id = test_plans.id
              ) = 1
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("test_plans") as batch_op:
        batch_op.drop_index("ix_test_plans_created_by")
        batch_op.drop_index("ix_test_plans_project_id")
        batch_op.drop_constraint(
            "fk_test_plans_creator",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_test_plans_project",
            type_="foreignkey",
        )
        batch_op.drop_column("created_by")
        batch_op.drop_column("project_id")
