"""数据库断言规则模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.database_types import JSONText


class DbAssertion(Base):
    """数据库断言规则."""
    __tablename__ = "db_assertions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    sql_template: Mapped[str] = mapped_column(Text)
    # SQL 模板支持变量: SELECT * FROM orders WHERE id = '${order_id}'
    expected_result: Mapped[dict] = mapped_column(JSONText, default=dict)
    # {"field": "status", "operator": "equals", "value": "paid"}
    # operator: equals / contains / greater_than / less_than / exists / count
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    test_case: Mapped["TestCase"] = relationship(  # noqa: F821
        back_populates="db_assertions"
    )
