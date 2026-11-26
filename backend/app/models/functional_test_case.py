"""功能测试用例模型.

与 API 自动化用例（``test_cases``）区分开：功能测试用例描述「谁在什么前置
条件下、执行哪些操作步骤、应得到什么结果」，不绑定 HTTP 请求定义，主要用于
人工执行与验收；API 用例则绑定 method/url/断言，由执行引擎自动跑。

AI 用例生成（``/test-design``）产出的用例草稿写入本表，不写入 ``test_cases``。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.database_types import JSONText


class FunctionalTestCase(Base):
    """一条功能测试用例：前置条件 + 操作步骤 + 预期结果."""

    __tablename__ = "functional_test_cases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(256), index=True)
    # 所属模块/分组路径，如 "登录与认证"
    module: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # 分类：功能 / 异常 / 边界 / 权限 / 安全
    category: Mapped[str] = mapped_column(String(16), default="功能")
    # 优先级：P0 / P1 / P2 / P3
    priority: Mapped[str] = mapped_column(String(8), default="P1", index=True)
    # 前置条件
    preconditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 操作步骤：字符串数组
    steps: Mapped[list] = mapped_column(JSONText, default=list)
    # 预期结果
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 需求追溯：来自需求中的哪句话
    trace_source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # 测试数据：[{"field": "分单号", "value": "XJ001", "note": "已存在"}]
    test_data: Mapped[list] = mapped_column(JSONText, default=list)
    # 可执行请求定义（接口形态用例）：导入后可直接由引擎执行
    request_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    request_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    request_headers: Mapped[dict] = mapped_column(JSONText, default=dict)
    request_body: Mapped[dict | list | None] = mapped_column(JSONText, nullable=True)
    assertions: Mapped[list] = mapped_column(JSONText, default=list)
    # 状态：draft 草稿 / active 可执行 / deprecated 已废弃
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    # 来源：ai 由 AI 生成 / manual 手工创建
    source: Mapped[str] = mapped_column(String(16), default="manual")
    # 关联需求
    requirement_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("requirements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 关联的 AI 生成会话（便于回溯）
    design_session_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
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


class FunctionalCaseExecution(Base):
    """功能测试用例的人工执行记录."""

    __tablename__ = "functional_case_executions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("functional_test_cases.id", ondelete="CASCADE"),
        index=True,
    )
    # 执行结果：passed / failed / blocked / skipped
    result: Mapped[str] = mapped_column(String(16), index=True)
    # 实际结果与备注
    actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 缺陷单号（外部系统）
    defect_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    executed_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    # 便于按轮次统计
    run_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_no: Mapped[int] = mapped_column(Integer, default=0)
