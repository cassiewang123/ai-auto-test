"""Dispatch persisted job terminal events to configured notification rules."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.execution_job import ExecutionJob
from app.models.notification_channel import NotificationChannel
from app.models.notification_log import NotificationLog
from app.models.notification_rule import NotificationRule
from app.services.notification_service import send_notification

logger = logging.getLogger(__name__)

_EVENT_ALIASES = {
    "job.completed": ("job.completed", "test_run.completed"),
    "job.failed": ("job.failed", "test_run.failed"),
    "job.timed_out": ("job.timed_out", "test_run.failed"),
    "job.quality_gate.failed": ("job.quality_gate.failed",),
}

NotificationSender = Callable[..., Awaitable[dict[str, Any]]]


def _metric(metrics: dict[str, Any] | None, key: str) -> int | float:
    if not metrics:
        return 0
    value = metrics.get(key, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0


def _failure_rate(metrics: dict[str, Any] | None) -> float:
    total = _metric(metrics, "total")
    failed = _metric(metrics, "failed")
    return failed / total if total else 0.0


def _rule_matches(
    rule: NotificationRule,
    context: dict[str, Any],
) -> bool:
    filters = rule.filters or {}
    metrics = context.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    min_failed_count = filters.get("min_failed_count")
    if (
        min_failed_count is not None
        and _metric(metrics, "failed") < int(min_failed_count)
    ):
        return False
    min_failure_rate = filters.get("min_failure_rate")
    if (
        min_failure_rate is not None
        and _failure_rate(metrics) < float(min_failure_rate)
    ):
        return False
    return not (
        filters.get("require_quality_gate_failure")
        and not context.get("quality_gate_failed")
    )


def build_job_notification_context(
    job: ExecutionJob,
    *,
    metrics: dict[str, Any] | None = None,
    quality_gates: list[dict[str, Any]] | None = None,
    defect_draft_id: str | None = None,
) -> dict[str, Any]:
    safe_metrics = metrics or {}
    gate_failed = any(
        isinstance(item, dict) and not item.get("passed", True)
        for item in (quality_gates or [])
    )
    return {
        "job_id": job.id,
        "job_type": job.job_type,
        "summary": job.result_summary,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "total": _metric(safe_metrics, "total"),
        "passed": _metric(safe_metrics, "passed"),
        "failed": _metric(safe_metrics, "failed"),
        "error": _metric(safe_metrics, "error"),
        "duration": _metric(safe_metrics, "duration"),
        "metrics": safe_metrics,
        "quality_gates": quality_gates or [],
        "quality_gate_failed": gate_failed,
        "defect_draft_id": defect_draft_id,
        "message": (
            job.result_summary
            or job.error_message
            or f"任务 {job.id} 已结束"
        ),
    }


def _event_aliases(event_type: str) -> tuple[str, ...] | None:
    return _EVENT_ALIASES.get(event_type)


def has_matching_rules(
    db: Session,
    job: ExecutionJob,
    event_type: str,
) -> bool:
    aliases = _event_aliases(event_type)
    if not aliases:
        return False
    statement = (
        select(NotificationRule.id)
        .join(
            NotificationChannel,
            NotificationChannel.id == NotificationRule.channel_id,
        )
        .where(
            NotificationRule.is_active.is_(True),
            NotificationChannel.is_active.is_(True),
            NotificationRule.event_type.in_(aliases),
            or_(
                NotificationRule.project_id.is_(None),
                NotificationRule.project_id == job.project_id,
            ),
        )
        .limit(1)
    )
    return db.execute(statement).scalar_one_or_none() is not None


async def dispatch_job_terminal_notifications(
    db: Session,
    job: ExecutionJob,
    event_type: str,
    context: dict[str, Any],
    sender: NotificationSender = send_notification,
) -> list[dict[str, Any]]:
    """Match active rules and record one notification log per dispatch."""
    aliases = _event_aliases(event_type)
    if not aliases:
        return []

    rows = db.execute(
        select(NotificationRule, NotificationChannel)
        .join(
            NotificationChannel,
            NotificationChannel.id == NotificationRule.channel_id,
        )
        .where(
            NotificationRule.is_active.is_(True),
            NotificationChannel.is_active.is_(True),
            NotificationRule.event_type.in_(aliases),
            or_(
                NotificationRule.project_id.is_(None),
                NotificationRule.project_id == job.project_id,
            ),
        )
    ).all()

    dispatched: list[dict[str, Any]] = []
    for rule, channel in rows:
        if not _rule_matches(rule, context):
            continue
        try:
            result = await sender(channel, rule.event_type, context)
            status = "success" if result.get("success") else "failed"
            message = result.get("message") or ""
        except Exception as exc:  # noqa: BLE001 - log and continue other rules
            logger.warning(
                "任务通知分发失败 job=%s rule=%s: %s",
                job.id,
                rule.id,
                exc,
            )
            status = "failed"
            message = str(exc)

        db.add(
            NotificationLog(
                channel_id=channel.id,
                project_id=job.project_id,
                channel_name=channel.name,
                event_type=rule.event_type,
                status=status,
                message=message[:4000] if message else None,
            )
        )
        dispatched.append(
            {
                "rule_id": rule.id,
                "channel_id": channel.id,
                "event_type": rule.event_type,
                "success": status == "success",
                "message": message,
            }
        )

    if dispatched:
        db.commit()
    return dispatched


def dispatch_job_terminal_notifications_sync(
    db: Session,
    job: ExecutionJob,
    event_type: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run dispatch from synchronous worker/API code when a rule exists."""
    if not has_matching_rules(db, job, event_type):
        return []
    return asyncio.run(
        dispatch_job_terminal_notifications(db, job, event_type, context)
    )
