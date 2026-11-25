"""缺陷集成模型：与外部缺陷跟踪系统（Jira/禅道/GitLab/Azure DevOps）集成."""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.sql import func

from app.database import Base


class DefectTicket(Base):
    __tablename__ = "defect_tickets"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id = Column(String(100), nullable=True)  # 外部系统 ID
    external_system = Column(String(50), nullable=True)  # jira/zentao/gitlab/azure_devops
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="open")  # open/in_progress/resolved/closed
    severity = Column(String(20), default="normal")  # critical/high/normal/low
    project_id = Column(String(36), nullable=True, index=True)
    test_result_id = Column(String(36), nullable=True)  # 关联的测试结果
    execution_job_id = Column(
        String(36),
        ForeignKey("execution_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # 关联的统一任务，供失败任务自动建单去重
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
