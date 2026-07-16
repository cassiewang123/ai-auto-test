"""AI 调用治理模型：记录每次 AI 调用的元数据、成本与人工反馈."""
from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base
import uuid


class AIInvocation(Base):
    __tablename__ = "ai_invocations"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    model = Column(String(100), nullable=True)
    provider = Column(String(50), nullable=True)
    prompt_version = Column(String(20), nullable=True)
    input_hash = Column(String(64), nullable=True)
    token_usage_input = Column(Integer, default=0)
    token_usage_output = Column(Integer, default=0)
    token_usage_total = Column(Integer, default=0)
    latency_ms = Column(Integer, nullable=True)
    cost = Column(Float, default=0.0)
    output_schema_valid = Column(Boolean, nullable=True)
    accepted = Column(Boolean, nullable=True)  # 人工反馈：采纳
    edited = Column(Boolean, nullable=True)  # 人工反馈：修改后采纳
    rejected = Column(Boolean, nullable=True)  # 人工反馈：拒绝
    feedback_comment = Column(Text, nullable=True)
    invoked_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIFeedback(Base):
    __tablename__ = "ai_feedback"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    invocation_id = Column(String(36), nullable=False, index=True)
    rating = Column(Integer, nullable=True)  # 1-5 星
    comment = Column(Text, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
