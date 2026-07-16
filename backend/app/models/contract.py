"""契约测试模型：契约版本与版本差异."""
from sqlalchemy import Column, String, Text, Integer, DateTime
from sqlalchemy.sql import func
from app.database import Base
import uuid


class ContractVersion(Base):
    __tablename__ = "contract_versions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contract_id = Column(String(36), nullable=False, index=True)  # 契约标识
    name = Column(String(200), nullable=False)
    version = Column(Integer, nullable=False)
    openapi_spec = Column(Text, nullable=True)  # JSON: OpenAPI 规范
    project_id = Column(String(36), nullable=True, index=True)
    status = Column(String(20), default="active")  # active/superseded
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ContractDiff(Base):
    __tablename__ = "contract_diffs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contract_id = Column(String(36), nullable=False, index=True)
    from_version = Column(Integer, nullable=False)
    to_version = Column(Integer, nullable=False)
    breaking_changes = Column(Text, nullable=True)  # JSON: 破坏性变更列表
    non_breaking_changes = Column(Text, nullable=True)  # JSON: 非破坏性变更
    affected_test_cases = Column(Text, nullable=True)  # JSON: 受影响的用例ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
