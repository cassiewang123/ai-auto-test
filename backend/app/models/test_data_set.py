"""数据驱动测试数据集模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.database_types import JSONText


class TestDataSet(Base):
    """数据驱动测试数据集：存储 CSV/JSON 参数化数据.

    data 字段存储原始 CSV 或 JSON 文本；
    variables 字段存储解析后的变量名列表，如 ["username", "password"]。
    """

    __tablename__ = "test_data_sets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(256), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # csv / json
    format: Mapped[str] = mapped_column(String(16))
    # 原始 CSV 或 JSON 文本
    data: Mapped[str] = mapped_column(Text)
    # 解析后的变量名列表，如 ["username", "password"]
    variables: Mapped[list] = mapped_column(JSONText, default=list)
    # 关联的测试用例，用例删除时级联删除数据集
    test_case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    test_case: Mapped["TestCase"] = relationship()  # noqa: F821
