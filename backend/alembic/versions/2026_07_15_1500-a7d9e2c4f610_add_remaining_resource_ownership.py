"""add remaining resource ownership

Revision ID: a7d9e2c4f610
Revises: c4e7a9b2d1f0
Create Date: 2026-07-15 15:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d9e2c4f610"
down_revision: str | None = "c4e7a9b2d1f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("call_history") as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("created_by", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_call_history_project",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_call_history_creator",
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_call_history_project_id",
            ["project_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_call_history_created_by",
            ["created_by"],
            unique=False,
        )

    op.execute(
        sa.text(
            """
            UPDATE call_history
            SET project_id = (
                SELECT tc.project_id
                FROM test_cases tc
                WHERE tc.id = call_history.test_case_id
            )
            WHERE project_id IS NULL
              AND test_case_id IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM test_cases tc
                  WHERE tc.id = call_history.test_case_id
                    AND tc.project_id IS NOT NULL
              )
            """
        )
    )

    with op.batch_alter_table("notification_logs") as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_notification_logs_project",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_notification_logs_project_id",
            ["project_id"],
            unique=False,
        )

    with op.batch_alter_table("notification_rules") as batch_op:
        batch_op.create_index(
            "ix_notification_rules_project_id",
            ["project_id"],
            unique=False,
        )

    with op.batch_alter_table("test_run_summaries") as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_test_run_summaries_creator",
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_test_run_summaries_project_id",
            ["project_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_test_run_summaries_created_by",
            ["created_by"],
            unique=False,
        )

    op.execute(
        sa.text(
            """
            UPDATE test_run_summaries
            SET project_id = (
                SELECT MIN(tc.project_id)
                FROM test_results tr
                JOIN test_cases tc ON tc.id = tr.test_case_id
                WHERE tr.run_id = test_run_summaries.run_id
                  AND tc.project_id IS NOT NULL
            )
            WHERE project_id IS NULL
              AND (
                  SELECT COUNT(*)
                  FROM test_results tr
                  WHERE tr.run_id = test_run_summaries.run_id
              ) > 0
              AND (
                  SELECT COUNT(*)
                  FROM test_results tr
                  LEFT JOIN test_cases tc ON tc.id = tr.test_case_id
                  WHERE tr.run_id = test_run_summaries.run_id
                    AND tc.project_id IS NULL
              ) = 0
              AND (
                  SELECT COUNT(DISTINCT tc.project_id)
                  FROM test_results tr
                  JOIN test_cases tc ON tc.id = tr.test_case_id
                  WHERE tr.run_id = test_run_summaries.run_id
              ) = 1
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE webhook_configs
            SET project_id = NULL
            WHERE project_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM projects p
                  WHERE p.id = webhook_configs.project_id
              )
            """
        )
    )

    with op.batch_alter_table("webhook_configs") as batch_op:
        batch_op.create_foreign_key(
            "fk_webhook_configs_project",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_webhook_configs_project_id",
            ["project_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("webhook_configs") as batch_op:
        batch_op.drop_index("ix_webhook_configs_project_id")
        batch_op.drop_constraint(
            "fk_webhook_configs_project",
            type_="foreignkey",
        )

    with op.batch_alter_table("test_run_summaries") as batch_op:
        batch_op.drop_index("ix_test_run_summaries_created_by")
        batch_op.drop_index("ix_test_run_summaries_project_id")
        batch_op.drop_constraint(
            "fk_test_run_summaries_creator",
            type_="foreignkey",
        )
        batch_op.drop_column("created_by")

    with op.batch_alter_table("notification_rules") as batch_op:
        batch_op.drop_index("ix_notification_rules_project_id")

    with op.batch_alter_table("notification_logs") as batch_op:
        batch_op.drop_index("ix_notification_logs_project_id")
        batch_op.drop_constraint(
            "fk_notification_logs_project",
            type_="foreignkey",
        )
        batch_op.drop_column("project_id")

    with op.batch_alter_table("call_history") as batch_op:
        batch_op.drop_index("ix_call_history_created_by")
        batch_op.drop_index("ix_call_history_project_id")
        batch_op.drop_constraint(
            "fk_call_history_creator",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_call_history_project",
            type_="foreignkey",
        )
        batch_op.drop_column("created_by")
        batch_op.drop_column("project_id")
