"""全局变量/工作空间变量模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GlobalVariable(Base):
    """全局/工作空间变量，执行时与环境变量合并使用.

    scope 取值：
        - global：全局变量，所有项目共享
        - workspace：工作空间变量，绑定到指定 project_id
    var_type 取值：string / number / boolean / json
    """

    __tablename__ = "global_variables"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), index=True)
    # Oracle stores empty strings as NULL; API serialization normalizes it.
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 变量类型：string / number / boolean / json
    var_type: Mapped[str] = mapped_column(String(16), default="string")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 作用域：global / workspace
    scope: Mapped[str] = mapped_column(String(16), default="global", index=True)
    # workspace 作用域时绑定的项目 ID（global 时为 None）
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
