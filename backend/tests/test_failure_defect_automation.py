"""Failure job defect draft automation tests."""
from __future__ import annotations

from app.models.defect_integration import DefectTicket
from app.models.project import Project
from app.services.execution.failure_defect_service import (
    create_failure_defect_draft,
)
from app.services.execution.job_service import JobService
from sqlalchemy import select


def _failed_execution_job(db_session, monkeypatch, *, project_id=None):
    service = JobService(db_session)
    job = service.create_job(
        job_type="api_case",
        project_id=project_id,
    )

    def fake_run(_service, running_job):
        return {
            "status": "failed",
            "summary": f"{running_job.id} failed",
            "error_code": "assertion_error",
            "error_message": "response status was 500",
            "metrics": {
                "total": 3,
                "passed": 1,
                "failed": 2,
                "error": 0,
                "skipped": 0,
                "duration": 0.5,
                "results": [],
            },
        }

    monkeypatch.setattr(JobService, "_run", fake_run)
    return service, service.execute_job(job.id, worker_id="defect-worker")


def test_failed_job_creates_deduplicated_defect_draft(
    db_session,
    monkeypatch,
):
    project = Project(
        id="defect-auto-project",
        name="自动缺陷项目",
        code="auto-defect",
    )
    db_session.add(project)
    db_session.commit()

    service, job = _failed_execution_job(
        db_session,
        monkeypatch,
        project_id=project.id,
    )

    assert job.status == "failed"
    tickets = (
        db_session.execute(
            select(DefectTicket).where(
                DefectTicket.execution_job_id == job.id
            )
        )
        .scalars()
        .all()
    )
    assert len(tickets) == 1
    ticket = tickets[0]
    assert ticket.project_id == project.id
    assert ticket.status == "open"
    assert ticket.severity == "high"
    assert "[任务失败]" in ticket.title
    assert "response status was 500" in ticket.description
    assert "result metrics" not in ticket.description

    second = create_failure_defect_draft(
        db_session,
        job,
        metrics={"failed": 2},
    )
    assert second is None

    events = service.get_events(job.id)
    terminal = next(
        event for event in events if event.event_type == "job.failed"
    )
    assert "defect_draft_id" in terminal.payload
    assert ticket.id in terminal.payload


def test_succeeded_job_does_not_create_defect_draft(
    db_session,
    monkeypatch,
):
    project = Project(id="defect-ok-project", name="无缺陷项目")
    db_session.add(project)
    db_session.commit()
    service = JobService(db_session)
    job = service.create_job(job_type="api_case", project_id=project.id)

    def fake_run(_service, running_job):
        return {
            "status": "succeeded",
            "summary": "ok",
            "metrics": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "error": 0,
            },
        }

    monkeypatch.setattr(JobService, "_run", fake_run)
    service.execute_job(job.id, worker_id="ok-worker")

    count = db_session.execute(
        select(DefectTicket).where(DefectTicket.execution_job_id == job.id)
    ).scalar_one_or_none()
    assert count is None
