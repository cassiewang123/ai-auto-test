"""Automatically create deduplicated defect drafts from failed jobs."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.defect_integration import DefectTicket
from app.models.execution_job import ExecutionJob

_JOB_TYPE_LABELS = {
    "api_case": "接口用例",
    "ui_case": "UI 用例",
    "ui_suite": "UI 套件",
    "performance": "性能测试",
    "ai_ui_optimize": "AI UI 优化",
}


def _safe_metrics_summary(metrics: dict[str, Any] | None) -> str:
    if not metrics:
        return ""
    values: list[str] = []
    for key in ("total", "passed", "failed", "error", "skipped", "duration"):
        value = metrics.get(key)
        if value is not None:
            values.append(f"{key}={value}")
    return " | ".join(values) if values else ""


def create_failure_defect_draft(
    db: Session,
    job: ExecutionJob,
    *,
    metrics: dict[str, Any] | None = None,
    quality_gates: list[dict[str, Any]] | None = None,
) -> DefectTicket | None:
    """Create one defect draft per failed execution job.

    The draft is added to the caller's transaction and flushed, so a normal
    terminal job commit persists both the job state and defect together.
    """
    if job.status not in {"failed", "timed_out"} or not job.project_id:
        return None

    existing_id = db.execute(
        select(DefectTicket.id).where(DefectTicket.execution_job_id == job.id)
    ).scalar_one_or_none()
    if existing_id:
        return None

    job_label = _JOB_TYPE_LABELS.get(job.job_type, job.job_type)
    title = f"[任务失败] {job_label} {job.id}"
    parts = [f"任务状态: {job.status}"]
    if job.error_code:
        parts.append(f"错误码: {job.error_code}")
    if job.error_message:
        parts.append(f"错误信息:\n{job.error_message}")
    if job.result_summary:
        parts.append(f"执行摘要:\n{job.result_summary}")
    metrics_summary = _safe_metrics_summary(metrics)
    if metrics_summary:
        parts.append(f"结果指标: {metrics_summary}")
    if quality_gates:
        failed_gates = [
            item
            for item in quality_gates
            if isinstance(item, dict) and not item.get("passed", True)
        ]
        if failed_gates:
            names = ", ".join(
                str(item.get("gate_name") or item.get("gate_id") or "?")
                for item in failed_gates
            )
            parts.append(f"未通过质量门禁: {names}")

    ticket = DefectTicket(
        title=title,
        description="\n".join(parts),
        status="open",
        severity="high",
        project_id=job.project_id,
        execution_job_id=job.id,
        created_by=job.created_by,
    )
    db.add(ticket)
    db.flush()
    return ticket
