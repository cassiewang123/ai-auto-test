"""接口用例库模型.

用于存放由「接口用例生成」产出的接口测试用例（方法/URL/参数/请求体/断言），
与 ``test_cases``（接口管理，用于执行）和 ``functional_test_cases``
（功能测试用例，人工执行）区分开，便于集中评审与导出。

用户可以一键把接口用例库中的用例发布到接口管理（``test_cases``）中执行；
本表本身只负责登记与导出台账。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class ApiCaseRecord(Base):
    """一条接口测试用例（接口用例库）."""

    __tablename__ = "api_case_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(256), index=True)
    method: Mapped[str] = mapped_column(String(16), default="GET")
    url: Mapped[str] = mapped_column(String(2048))
    headers: Mapped[dict] = mapped_column(JSONText, default=dict)
    params: Mapped[dict] = mapped_column(JSONText, default=dict)
    body: Mapped[dict | list | None] = mapped_column(JSONText, nullable=True)
    assertions: Mapped[list] = mapped_column(JSONText, default=list)

    # 场景类型：normal / exception / boundary / permission
    case_type: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    priority: Mapped[str] = mapped_column(String(8), default="P1", index=True)
    # 状态：draft 草稿 / active 已确认 / archived 已归档
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    # 来源：ai 生成 / manual 手工
    source: Mapped[str] = mapped_column(String(16), default="ai")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 关联接口/分组，便于按模块统计
    interface_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    group_path: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
