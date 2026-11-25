"""Job terminal notification dispatch tests."""
from __future__ import annotations

import asyncio

from app.models.execution_job import ExecutionJob
from app.models.notification_channel import NotificationChannel
from app.models.notification_log import NotificationLog
from app.models.notification_rule import NotificationRule
from app.models.project import Project
from app.services import notification_service as ns
from app.services.execution.job_notification_service import (
    build_job_notification_context,
    dispatch_job_terminal_notifications,
    has_matching_rules,
)
from app.services.execution.job_service import JobService
from sqlalchemy import select


def _ready_job(db_session, *, project_id: str | None, status: str) -> ExecutionJob:
    service = JobService(db_session)
    job = service.create_job(job_type="api_case", project_id=project_id)
    job.status = status
    job.result_summary = "finished"
    job.error_message = "boom" if status in {"failed", "timed_out"} else None
    db_session.commit()
    db_session.refresh(job)
    return job


def _channel_and_rule(
    db_session,
    *,
    project_id: str | None,
    event_type: str = "job.completed",
    is_active: bool = True,
    filters: dict | None = None,
):
    channel = NotificationChannel(
        name="dispatch-channel",
        type="feishu",
        webhook_url="https://example.com/hook",
        secret=None,
        is_active=True,
    )
    db_session.add(channel)
    db_session.flush()
    rule = NotificationRule(
        name="dispatch-rule",
        channel_id=channel.id,
        event_type=event_type,
        project_id=project_id,
        filters=filters,
        is_active=is_active,
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return channel, rule


async def _fake_sender(channel, event_type, context):
    return {"success": True, "message": f"sent {event_type}"}


def test_job_completed_matches_project_rule_and_records_log(db_session):
    project = Project(id="notify-project", name="通知项目")
    db_session.add(project)
    db_session.commit()
    job = _ready_job(
        db_session,
        project_id=project.id,
        status="succeeded",
    )
    channel, rule = _channel_and_rule(
        db_session,
        project_id=project.id,
    )
    context = build_job_notification_context(job, metrics={"total": 2, "passed": 2})

    assert has_matching_rules(db_session, job, "job.completed") is True
    outcomes = asyncio.run(
        dispatch_job_terminal_notifications(
            db_session,
            job,
            "job.completed",
            context,
            sender=_fake_sender,
        )
    )

    assert outcomes == [
        {
            "rule_id": rule.id,
            "channel_id": channel.id,
            "event_type": "job.completed",
            "success": True,
            "message": "sent job.completed",
        }
    ]
    log = db_session.execute(
        select(NotificationLog).where(NotificationLog.channel_id == channel.id)
    ).scalar_one()
    assert log.event_type == "job.completed"
    assert log.project_id == project.id
    assert log.status == "success"


def test_dispatch_skips_other_project_and_inactive_rules(db_session):
    project = Project(id="other-project", name="其他项目")
    db_session.add(project)
    db_session.commit()
    job = _ready_job(
        db_session,
        project_id=project.id,
        status="failed",
    )
    _channel_and_rule(
        db_session,
        project_id="different-project",
        event_type="job.failed",
    )
    _channel_and_rule(
        db_session,
        project_id=project.id,
        event_type="job.failed",
        is_active=False,
    )
    context = build_job_notification_context(job, metrics={"failed": 1})

    outcomes = asyncio.run(
        dispatch_job_terminal_notifications(
            db_session,
            job,
            "job.failed",
            context,
            sender=_fake_sender,
        )
    )

    assert outcomes == []
    assert (
        db_session.execute(select(NotificationLog)).scalars().first() is None
    )


def test_job_failed_message_includes_job_and_error() -> None:
    message = ns.format_message(
        "job.failed",
        {
            "job_id": "job-1",
            "error_message": "assert failed",
        },
    )
    assert "统一任务失败" in message
    assert "job-1" in message
    assert "assert failed" in message


def test_quality_gate_failed_message_includes_failed_gates() -> None:
    message = ns.format_message(
        "job.quality_gate.failed",
        {
            "job_id": "job-1",
            "quality_gates": [
                {
                    "gate_id": "gate-1",
                    "gate_name": "通过率门禁",
                    "passed": False,
                }
            ],
        },
    )
    assert "质量门禁未通过" in message
    assert "通过率门禁" in message


def test_dispatch_skips_rules_below_failure_threshold(db_session):
    project = Project(id="threshold-project", name="阈值项目")
    db_session.add(project)
    db_session.commit()
    job = _ready_job(
        db_session,
        project_id=project.id,
        status="failed",
    )
    _channel_and_rule(
        db_session,
        project_id=project.id,
        event_type="job.failed",
        filters={"min_failed_count": 3},
    )
    context = build_job_notification_context(
        job,
        metrics={"total": 10, "passed": 9, "failed": 1},
    )

    outcomes = asyncio.run(
        dispatch_job_terminal_notifications(
            db_session,
            job,
            "job.failed",
            context,
            sender=_fake_sender,
        )
    )

    assert outcomes == []
