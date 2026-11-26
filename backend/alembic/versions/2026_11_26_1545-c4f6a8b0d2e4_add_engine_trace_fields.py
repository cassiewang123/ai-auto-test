"""add engine model and fallback reason to design sessions

Revision ID: c4f6a8b0d2e4
Revises: f0a1b2c3d4e5
Create Date: 2026-11-26 15:45:00

用户需要能判断某次 AI 生成是「大模型产出」还是「规则引擎兜底」，以及回退
的具体原因（未启用、超时、输出被截断等）。仅靠 engine 一个枚举值不够，
补两个字段：

- ``engine_model``：实际使用的模型名（engine=llm 时有值）
- ``engine_fallback_reason``：回退到规则引擎的原因说明

历史数据两个字段留空，语义为「未知」。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4f6a8b0d2e4"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("test_design_sessions") as batch:
        batch.add_column(sa.Column("engine_model", sa.String(length=128)))
        batch.add_column(sa.Column("engine_fallback_reason", sa.Text()))


def downgrade() -> None:
    with op.batch_alter_table("test_design_sessions") as batch:
        batch.drop_column("engine_fallback_reason")
        batch.drop_column("engine_model")
