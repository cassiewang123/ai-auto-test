"""压测服务器监控指标模型（功能15）."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PerfMetric(Base):
    """压测期间的服务器监控指标（每秒一条）."""

    __tablename__ = "perf_metrics"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    test_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("performance_tests.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    result_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("performance_results.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    # 相对压测开始的秒数
    elapsed: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    cpu: Mapped[float] = mapped_column(Float, default=0.0)  # CPU 使用率 %
    memory: Mapped[float] = mapped_column(Float, default=0.0)  # 内存使用率 %
    disk_read: Mapped[float] = mapped_column(Float, default=0.0)  # 磁盘读 KB/s
    disk_write: Mapped[float] = mapped_column(Float, default=0.0)  # 磁盘写 KB/s
    net_sent: Mapped[float] = mapped_column(Float, default=0.0)  # 网络发送 KB/s
    net_recv: Mapped[float] = mapped_column(Float, default=0.0)  # 网络接收 KB/s
