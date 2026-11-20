"""需求文档、需求分析与 AI 测试设计相关请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 需求文档
# ---------------------------------------------------------------------------
class RequirementDocumentResponse(BaseModel):
    """需求附件文档响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    requirement_id: str
    filename: str
    file_type: str
    file_size: int = 0
    char_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class RequirementDocumentImportRequest(BaseModel):
    """由「文档导入」创建需求：上传解析后由前端提交."""

    title: str = Field(..., min_length=1, max_length=256)
    content: str | None = None
    priority: str = "P1"
    project_id: str | None = None


# ---------------------------------------------------------------------------
# 需求分析
# ---------------------------------------------------------------------------
class RequirementAnalysisRequest(BaseModel):
    """发起需求分析."""

    knowledge_base_id: str | None = Field(
        default=None, description="可选：引用知识库提供技术/业务上下文"
    )
    question: str | None = Field(
        default=None, description="可选：追加的对话指令（补充、调整或重新梳理）"
    )
    use_documents: bool = Field(
        default=True, description="是否把需求附件文档正文纳入分析"
    )


class FunctionItem(BaseModel):
    """功能清单条目."""

    module: str = ""
    points: list[str] = Field(default_factory=list)


class UiDescription(BaseModel):
    """界面描述条目."""

    page: str = ""
    description: str = ""


class Clarification(BaseModel):
    """待澄清项."""

    question: str = ""
    reason: str = ""


class RequirementAnalysisResponse(BaseModel):
    """需求分析结果."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    requirement_id: str
    engine: str = "rule"
    knowledge_base_id: str | None = None
    function_items: list[FunctionItem] = Field(default_factory=list)
    ui_descriptions: list[UiDescription] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(default_factory=list)
    markdown: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RequirementAnalysisMessageRequest(BaseModel):
    """在多轮对话窗口中追加一条指令并重新分析."""

    message: str = Field(..., min_length=1, description="测试人员输入的补充/调整要求")


# ---------------------------------------------------------------------------
# AI 测试设计会话
# ---------------------------------------------------------------------------
class TestDesignSessionCreate(BaseModel):
    """创建生成会话."""

    title: str | None = Field(default=None, max_length=256)
    project_id: str | None = None
    requirement_id: str | None = None
    knowledge_base_id: str | None = None
    mode: str = Field(default="quick", description="quick 快速生成 / stepwise 分步生成")
    prompt: str | None = Field(default=None, description="要测范围的补充描述")
    review_dimensions: dict[str, int] = Field(
        default_factory=dict, description="评审维度权重：{维度名: 1-5}"
    )


class TestPointItem(BaseModel):
    """测试点."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    order: int = 0
    module: str = ""
    point: str = ""
    category: str = "功能"
    priority: str = "P1"
    selected: bool = True
    trace_source: str | None = None


class TestPointUpdateItem(BaseModel):
    """测试点编辑（人工修改或删除）."""

    id: str
    module: str | None = None
    point: str | None = None
    category: str | None = None
    priority: str | None = None
    selected: bool | None = None


class TestPointBulkUpdateRequest(BaseModel):
    """批量确认/修改测试点."""

    points: list[TestPointUpdateItem] = Field(default_factory=list)


class GeneratedCaseItem(BaseModel):
    """用例草稿."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    order: int = 0
    title: str
    module: str = ""
    category: str = "功能"
    priority: str = "P1"
    preconditions: str | None = None
    steps: list[str] = Field(default_factory=list)
    expected: str | None = None
    trace_source: str | None = None
    selected: bool = True
    imported_case_id: str | None = None


class TestDesignSessionResponse(BaseModel):
    """生成会话详情."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None = None
    project_id: str | None = None
    requirement_id: str | None = None
    requirement_title: str | None = None
    knowledge_base_id: str | None = None
    knowledge_base_name: str | None = None
    mode: str = "quick"
    status: str = "clarifying"
    engine: str = "rule"
    review_dimensions: dict[str, int] = Field(default_factory=dict)
    prompt: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_refs: list[dict[str, Any]] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)
    test_points: list[TestPointItem] = Field(default_factory=list)
    cases: list[GeneratedCaseItem] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SessionMessageRequest(BaseModel):
    """会话继续对话（补充信息或要求修改）."""

    message: str = Field(..., min_length=1)


class GenerateCasesRequest(BaseModel):
    """基于已确认测试点生成用例."""

    point_ids: list[str] | None = Field(
        default=None, description="为空时使用全部已勾选测试点"
    )


class ReviewRequest(BaseModel):
    """多维度评审请求."""

    dimensions: dict[str, int] = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    """多维度评审结果."""

    overall_score: float = 0.0
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    dimensions: dict[str, int] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class ImportCasesRequest(BaseModel):
    """把选中的用例草稿写入用例库."""

    case_ids: list[str] | None = Field(
        default=None, description="为空时写入全部已勾选用例"
    )
    project_id: str | None = None


class ImportCasesResponse(BaseModel):
    """写入结果."""

    created_count: int = 0
    test_case_ids: list[str] = Field(default_factory=list)
