"""API 接口分组模型.

接口用例通过 ``TestCase.group_path`` 归入分组（如 ``swgd-imap-content/ApiType 码表``）。
本表用于显式维护分组本身，使分组可以独立存在（即使暂时没有接口），并支持
新建、重命名与说明维护。

约定：``path`` 是完整路径，``name`` 是路径的最后一段。重命名分组时会同步更新
所有 ``group_path`` 落在该分组（含子分组）下的用例。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ApiGroup(Base):
    """一个接口分组节点."""

    __tablename__ = "api_groups"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # 完整分组路径，如 "swgd-imap-content/ApiType 码表"
    path: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # 最后一段名称
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 父级路径，空表示顶级模块
    parent_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 是否置顶/排序，越小越靠前
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
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
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
