"""add executable fields to generated cases and output mode to sessions

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-11-26 09:30:00

让 AI 用例生成能产出「可执行」内容：

- ``test_design_sessions.output_mode``：manual 人工执行 / api 接口自动化；
- ``generated_cases.test_data``：本用例实际使用的字段与取值；
- ``generated_cases.request_*`` 与 ``assertions``：接口形态用例的请求定义
  与断言，导入后可由执行引擎直接跑。

历史数据按默认值处理：会话沿用 manual，用例的可执行字段为空。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("test_design_sessions") as batch:
        batch.add_column(
            sa.Column(
                "output_mode",
                sa.String(length=16),
                nullable=False,
                server_default="manual",
            )
        )

    with op.batch_alter_table("generated_cases") as batch:
        batch.add_column(
            sa.Column(
                "test_data", sa.Text(), nullable=False, server_default="[]"
            )
        )
        batch.add_column(sa.Column("request_method", sa.String(length=16)))
        batch.add_column(sa.Column("request_url", sa.String(length=2048)))
        batch.add_column(
            sa.Column(
                "request_headers", sa.Text(), nullable=False, server_default="{}"
            )
        )
        batch.add_column(sa.Column("request_body", sa.Text()))
        batch.add_column(
            sa.Column(
                "assertions", sa.Text(), nullable=False, server_default="[]"
            )
        )

    # 功能用例库同样保存测试数据与可执行请求，便于人工按数据执行
    with op.batch_alter_table("functional_test_cases") as batch:
        batch.add_column(
            sa.Column(
                "test_data", sa.Text(), nullable=False, server_default="[]"
            )
        )
        batch.add_column(sa.Column("request_method", sa.String(length=16)))
        batch.add_column(sa.Column("request_url", sa.String(length=2048)))
        batch.add_column(
            sa.Column(
                "request_headers", sa.Text(), nullable=False, server_default="{}"
            )
        )
        batch.add_column(sa.Column("request_body", sa.Text()))
        batch.add_column(
            sa.Column(
                "assertions", sa.Text(), nullable=False, server_default="[]"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("functional_test_cases") as batch:
        batch.drop_column("assertions")
        batch.drop_column("request_body")
        batch.drop_column("request_headers")
        batch.drop_column("request_url")
        batch.drop_column("request_method")
        batch.drop_column("test_data")

    with op.batch_alter_table("generated_cases") as batch:
        batch.drop_column("assertions")
        batch.drop_column("request_body")
        batch.drop_column("request_headers")
        batch.drop_column("request_url")
        batch.drop_column("request_method")
        batch.drop_column("test_data")

    with op.batch_alter_table("test_design_sessions") as batch:
        batch.drop_column("output_mode")
