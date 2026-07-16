"""质量门禁模型：门禁规则与评估结果."""
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base
import uuid


class QualityGate(Base):
    __tablename__ = "quality_gates"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    project_id = Column(String(36), nullable=True, index=True)
    rules = Column(Text, nullable=True)  # JSON: 门禁规则
    mode = Column(String(20), default="block")  # block/warn/log
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class QualityGateResult(Base):
    __tablename__ = "quality_gate_results"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    gate_id = Column(String(36), nullable=False, index=True)
    project_id = Column(String(36), nullable=True)
    run_id = Column(String(36), nullable=True)  # 关联的执行记录
    passed = Column(Boolean, nullable=False)
    results = Column(Text, nullable=True)  # JSON: 各规则评估结果
    triggered_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
