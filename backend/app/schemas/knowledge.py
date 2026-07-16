"""知识工程相关的请求/响应模型：缺陷模式、业务规则、接口知识."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 缺陷模式 DefectPattern
# ---------------------------------------------------------------------------
class DefectPatternBase(BaseModel):
    """缺陷模式基础字段."""

    title: str = Field(..., max_length=256, description="缺陷模式标题")
    description: str = Field(..., description="缺陷模式描述")
    pattern_type: str = Field(
        ..., max_length=32, description="缺陷类型: concurrency/null_pointer/boundary/auth/data_integrity/timeout/unknown"
    )
    related_interface: str | None = Field(default=None, max_length=2048, description="关联接口")
    related_case_id: str | None = Field(default=None, max_length=36, description="关联用例ID")
    severity: str = Field(default="medium", max_length=16, description="严重等级: critical/high/medium/low")
    occurrence_count: int = Field(default=1, ge=0, description="出现次数")
    source: str = Field(default="ai_analysis", max_length=32, description="来源: ai_analysis/manual")
    ai_analysis_snapshot: dict[str, Any] | None = Field(default=None, description="AI分析快照")
    is_active: bool = Field(default=True, description="是否激活")
    project_id: str | None = Field(default=None, max_length=36, description="项目ID")


class DefectPatternCreate(DefectPatternBase):
    """创建缺陷模式."""

    pass


class DefectPatternUpdate(BaseModel):
    """更新缺陷模式，全部字段可选."""

    title: str | None = None
    description: str | None = None
    pattern_type: str | None = None
    related_interface: str | None = None
    related_case_id: str | None = None
    severity: str | None = None
    occurrence_count: int | None = None
    source: str | None = None
    ai_analysis_snapshot: dict[str, Any] | None = None
    is_active: bool | None = None
    project_id: str | None = None


class DefectPatternResponse(DefectPatternBase):
    """缺陷模式响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# 业务规则 BusinessRule
# ---------------------------------------------------------------------------
class BusinessRuleBase(BaseModel):
    """业务规则基础字段."""

    title: str = Field(..., max_length=256, description="规则标题")
    rule_text: str = Field(..., description="规则内容")
    rule_type: str = Field(
        ..., max_length=32, description="规则类型: test_point/boundary/exception/data_validation/security"
    )
    project_id: str | None = Field(default=None, max_length=36, description="项目ID")
    module: str | None = Field(default=None, max_length=128, description="模块")
    related_defect_id: str | None = Field(default=None, max_length=36, description="关联缺陷模式ID")
    source: str = Field(default="manual", max_length=32, description="来源: manual/ai_extracted/defect_promoted")
    priority: str = Field(default="P1", max_length=16, description="优先级")
    is_active: bool = Field(default=True, description="是否激活")


class BusinessRuleCreate(BusinessRuleBase):
    """创建业务规则."""

    pass


class BusinessRuleUpdate(BaseModel):
    """更新业务规则，全部字段可选."""

    title: str | None = None
    rule_text: str | None = None
    rule_type: str | None = None
    project_id: str | None = None
    module: str | None = None
    related_defect_id: str | None = None
    source: str | None = None
    priority: str | None = None
    is_active: bool | None = None


class BusinessRuleResponse(BusinessRuleBase):
    """业务规则响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# 接口知识 InterfaceKnowledge
# ---------------------------------------------------------------------------
class InterfaceKnowledgeBase(BaseModel):
    """接口知识基础字段."""

    project_id: str | None = Field(default=None, max_length=36, description="项目ID")
    interface_path: str = Field(..., max_length=2048, description="接口路径")
    method: str = Field(..., max_length=8, description="HTTP方法")
    field_meanings: dict[str, Any] | None = Field(default=None, description="字段含义")
    dependencies: list[Any] | None = Field(default=None, description="依赖接口")
    common_headers: dict[str, Any] | None = Field(default=None, description="常用请求头")
    notes: str | None = Field(default=None, description="备注")
    source: str = Field(default="manual", max_length=32, description="来源: manual/ai_extracted")


class InterfaceKnowledgeCreate(InterfaceKnowledgeBase):
    """创建接口知识."""

    pass


class InterfaceKnowledgeUpdate(BaseModel):
    """更新接口知识，全部字段可选."""

    project_id: str | None = None
    interface_path: str | None = None
    method: str | None = None
    field_meanings: dict[str, Any] | None = None
    dependencies: list[Any] | None = None
    common_headers: dict[str, Any] | None = None
    notes: str | None = None
    source: str | None = None


class InterfaceKnowledgeResponse(InterfaceKnowledgeBase):
    """接口知识响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
