"""UI 视觉回归基线模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VisualBaseline(Base):
    """UI 视觉回归基线截图.

    每条基线关联一个 UI 测试用例，存储基线截图（base64 字符串），
    在执行用例时与最新截图对比，diff_score <= threshold 视为通过。
    """

    __tablename__ = "visual_baselines"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ui_test_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ui_test_cases.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(256))  # 基线名称
    screenshot_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # 可选：截图文件路径
    baseline_image: Mapped[str] = mapped_column(Text)  # base64 编码的基线图片
    threshold: Mapped[float] = mapped_column(Float, default=0.1)  # 差异阈值
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class VisualDiffResult(Base):
    """视觉回归对比结果.

    每次执行 UI 用例（若有基线）会产生一条对比结果记录。
    """

    __tablename__ = "visual_diff_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ui_test_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ui_test_records.id", ondelete="CASCADE"), index=True
    )
    baseline_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("visual_baselines.id", ondelete="CASCADE"), index=True
    )
    diff_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1 差异比例
    diff_image: Mapped[str | None] = mapped_column(Text, nullable=True)  # base64 差异图
    passed: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
