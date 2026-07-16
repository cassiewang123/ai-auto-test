"""测试计划与计划项模型."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.database_types import JSONText

if TYPE_CHECKING:
    from app.models.test_case import TestCase


class TestPlan(Base):
    """测试计划：组合多个用例，可指定环境与执行策略."""

    __tablename__ = "test_plans"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(256), index=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    environment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("environments.id"), nullable=True
    )
    # 执行模式：sequential / parallel / stress
    execution_mode: Mapped[str] = mapped_column(String(16), default="sequential")
    # 标记筛选：仅执行匹配标记的用例
    marker_filter: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 压测参数（JSON）：{"users": 100, "spawn_rate": 10, "duration": "5m"}
    stress_config: Mapped[dict | None] = mapped_column(JSONText, default=None)
    # 场景类型：single 独立用例执行 / chain 串联执行支持变量传递
    scenario_type: Mapped[str] = mapped_column(String(16), default="single")
    # 失败策略：stop 遇失败中断（串联模式默认）/ continue 继续执行后续用例
    fail_strategy: Mapped[str] = mapped_column(String(16), default="stop")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[TestPlanItem]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class TestPlanItem(Base):
    """计划项：计划与用例的多对多关联，带执行顺序."""

    __tablename__ = "test_plan_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_plans.id", ondelete="CASCADE"), index=True
    )
    test_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), index=True
    )
    order: Mapped[int] = mapped_column(Integer, default=0)

    plan: Mapped[TestPlan] = relationship(back_populates="items")
    test_case: Mapped[TestCase] = relationship(
        back_populates="plan_items"
    )
