"""DAG 工作流模型：工作流定义与运行记录."""
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base
import uuid


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    project_id = Column(String(36), nullable=True, index=True)
    nodes = Column(Text, nullable=True)  # JSON: DAG 节点定义
    edges = Column(Text, nullable=True)  # JSON: DAG 边定义
    version = Column(Integer, default=1)
    status = Column(String(20), default="draft")  # draft/published/deprecated
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), nullable=False, index=True)
    workflow_version = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")  # pending/running/succeeded/failed/cancelled
    context = Column(Text, nullable=True)  # JSON: 运行时上下文和变量
    node_results = Column(Text, nullable=True)  # JSON: 各节点执行结果
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
