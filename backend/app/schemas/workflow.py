"""DAG 工作流的请求/响应模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowDefinitionBase(BaseModel):
    """工作流定义基础字段."""

    name: str = Field(..., max_length=200, description="工作流名称")
    description: str | None = Field(default=None, description="描述")
    project_id: str | None = Field(default=None, max_length=36, description="项目 ID")
    nodes: list[dict[str, Any]] | None = Field(default=None, description="DAG 节点定义")
    edges: list[dict[str, Any]] | None = Field(default=None, description="DAG 边定义")


class WorkflowDefinitionCreate(WorkflowDefinitionBase):
    """创建工作流."""

    pass


class WorkflowDefinitionUpdate(BaseModel):
    """更新工作流，全部字段可选."""

    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    project_id: str | None = Field(default=None, max_length=36)
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    status: str | None = Field(default=None, max_length=20)


class WorkflowDefinitionResponse(BaseModel):
    """工作流定义响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    project_id: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    version: int = 1
    status: str = "draft"
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkflowRunCreate(BaseModel):
    """执行工作流的请求."""

    context: dict[str, Any] | None = Field(default=None, description="运行时上下文和变量")


class WorkflowRunResponse(BaseModel):
    """工作流运行记录响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    workflow_version: int | None = None
    status: str = "pending"
    context: dict[str, Any] | None = None
    node_results: list[dict[str, Any]] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
