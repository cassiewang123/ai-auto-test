"""UI 测试套件模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class UiTestSuite(Base):
    """UI 测试套件：聚合多个 UI 用例，支持批量执行."""

    __tablename__ = "ui_test_suites"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(256), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_ids: Mapped[list] = mapped_column(JSONText, default=list)  # 用例 ID 列表
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 执行模式：sequential 顺序执行 / parallel 并行执行
    execution_mode: Mapped[str] = mapped_column(String(20), default="sequential")
    # 并行执行时的最大并发数
    max_workers: Mapped[int] = mapped_column(Integer, default=4)
    # 是否启用失败重试（开启后套件内用例按各自 retry_count 自动重试）
    retry_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class UiTestSuiteRun(Base):
    """UI 测试套件执行记录：一次批量执行产生的汇总.

    id 字段即 run_id，记录本次执行包含的所有 UiTestRecord id 列表，
    供 JUnit XML 报告生成使用。
    """

    __tablename__ = "ui_test_suite_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ui_test_suites.id", ondelete="CASCADE"), index=True
    )
    suite_name: Mapped[str] = mapped_column(String(256))
    project_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/completed/failed
    record_ids: Mapped[list] = mapped_column(JSONText, default=list)  # 关联的 UiTestRecord id 列表
    triggered_by: Mapped[str] = mapped_column(String(128), default="manual")
    # 本次执行使用的执行模式（冗余记录，便于回溯）
    execution_mode: Mapped[str] = mapped_column(String(20), default="sequential")
    # 本次执行使用的最大并发数
    max_workers: Mapped[int] = mapped_column(Integer, default=1)
    # 并行模式下的串行预估总耗时（各用例耗时之和），用于计算加速比；顺序模式为 None
    parallel_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 是否启用失败重试（执行时的快照）
    retry_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 总重试次数（所有用例额外尝试次数之和）
    total_retries: Mapped[int] = mapped_column(Integer, default=0)
    # 重试过的用例列表 [{case_id, case_title, attempts}]
    retried_cases: Mapped[list] = mapped_column(JSONText, default=list)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
