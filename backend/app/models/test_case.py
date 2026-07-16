"""测试用例与断言规则模型."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.database_types import JSONText


class TestCase(Base):
    """接口测试用例定义."""

    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(256), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 分组/模块路径，如 "用户管理/认证"
    group_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # 标记：["smoke", "api", "regression"]
    markers: Mapped[list] = mapped_column(JSONText, default=list)

    # 请求定义
    method: Mapped[str] = mapped_column(String(16))  # GET/POST/PUT/PATCH/DELETE
    url: Mapped[str] = mapped_column(String(2048))
    headers: Mapped[dict] = mapped_column(JSONText, default=dict)
    params: Mapped[dict] = mapped_column(JSONText, default=dict)
    body: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    # GraphQL 专用
    graphql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 文件上传
    files: Mapped[list | None] = mapped_column(JSONText, nullable=True)

    # 变量提取规则：[{"name": "token", "source": "body", "expression": "$.access_token"}]
    extract_rules: Mapped[list] = mapped_column(JSONText, default=list)

    # 失败重试配置
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_interval: Mapped[float] = mapped_column(Float, default=1.0)

    # 前置/后置脚本（Python 代码，在受限命名空间执行）
    pre_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_script: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 排序权重，数值越小越靠前
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    environment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("environments.id"), nullable=True
    )
    # 所属项目
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # --- Phase 4 用例版本管理 ---
    # 版本号，每次发布 +1
    version: Mapped[int] = mapped_column(Integer, default=1)
    # 用例状态：draft / review / published / deprecated
    case_status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # 审核人
    reviewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # 审批人
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # 发布时间
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 父用例 ID（版本链）：发布新版本时，旧版本作为新版本的父用例
    parent_case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    environment: Mapped["Environment"] = relationship(  # noqa: F821
        back_populates="test_cases"
    )
    project: Mapped["Project"] = relationship(  # noqa: F821
        back_populates="test_cases", foreign_keys=[project_id]
    )
    assertions: Mapped[list["AssertionRule"]] = relationship(
        back_populates="test_case", cascade="all, delete-orphan"
    )
    db_assertions: Mapped[list["DbAssertion"]] = relationship(
        back_populates="test_case", cascade="all, delete-orphan"
    )
    plan_items: Mapped[list["TestPlanItem"]] = relationship(  # noqa: F821
        back_populates="test_case"
    )


class AssertionRule(Base):
    """断言规则，属于某个测试用例."""

    __tablename__ = "assertion_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    test_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), index=True
    )
    # 断言类型：status_code / json_path / header / response_time / json_schema
    assertion_type: Mapped[str] = mapped_column(String(32))
    # 表达式：JSONPath、Header 名、JSON Schema 等
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 比较操作符：eq / ne / gt / lt / ge / le / contains / regex / type
    operator: Mapped[str] = mapped_column(String(16), default="eq")
    # 期望值（JSON 编码以支持多种类型）
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 优先级 P0-P3
    priority: Mapped[str] = mapped_column(String(4), default="P1")
    order: Mapped[int] = mapped_column(Integer, default=0)

    test_case: Mapped["TestCase"] = relationship(back_populates="assertions")
