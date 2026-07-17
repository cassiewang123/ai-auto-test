"""Focused coverage for unified CallHistory and ExecutionJob history."""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import create_app
from app.models.call_history import CallHistory
from app.models.execution_job import ExecutionJob
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.test_case import TestCase as ApiTestCase
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.execution.job_reporting import RESULT_METRICS_CONFIG_KEY


def _user(user_id: str, *, superuser: bool = False) -> User:
    return User(
        id=user_id,
        username=user_id,
        email=f"{user_id}@test.local",
        hashed_password="not-used",
        is_active=True,
        is_superuser=superuser,
    )


def _client(db_session, current: dict[str, User]) -> TestClient:
    app = create_app()

    def override_db():
        yield db_session

    def override_user():
        return current["user"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app)


def _job(
    *,
    job_id: str,
    status: str,
    project_id: str,
    created_by: str,
    resource_id: str,
    created_at: datetime,
    duration: float,
) -> ExecutionJob:
    counts = {
        "succeeded": (1, 0, 0, 0),
        "failed": (0, 1, 0, 0),
        "timed_out": (0, 0, 1, 0),
        "cancelled": (0, 0, 0, 1),
    }
    passed, failed, error, skipped = counts[status]
    return ExecutionJob(
        id=job_id,
        job_type="api_case",
        resource_id=resource_id,
        project_id=project_id,
        created_by=created_by,
        status=status,
        result_summary=f"{status} summary",
        created_at=created_at,
        started_at=created_at,
        finished_at=created_at,
        config={
            RESULT_METRICS_CONFIG_KEY: {
                "total": 1,
                "passed": passed,
                "failed": failed,
                "error": error,
                "skipped": skipped,
                "duration": duration,
                "status_code": 200 if status == "succeeded" else None,
            }
        },
    )


def test_history_aggregates_jobs_filters_stats_and_preserves_deletion(
    db_session,
    client,
):
    project = Project(id="history-project", name="History Project")
    case = ApiTestCase(
        id="history-case",
        title="Health check",
        method="GET",
        url="https://example.test/health",
        project_id=project.id,
    )
    call = CallHistory(
        id="history-call",
        method="POST",
        url="https://example.test/login",
        status="passed",
        duration=0.5,
        source="quick_test",
        project_id=project.id,
        created_by="test-admin-id",
        executed_at=datetime(2026, 7, 17, 9, 0),
    )
    jobs = [
        _job(
            job_id=f"history-job-{status}",
            status=status,
            project_id=project.id,
            created_by="test-admin-id",
            resource_id=case.id,
            created_at=datetime(2026, 7, 17, 10, index),
            duration=float(index),
        )
        for index, status in enumerate(
            ("succeeded", "failed", "timed_out", "cancelled"),
            start=1,
        )
    ]
    db_session.add_all([project, case, call, *jobs])
    db_session.commit()
    call_id = call.id

    response = client.get("/api/v1/history")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 5
    assert [item["id"] for item in payload["data"][:4]] == [
        "history-job-cancelled",
        "history-job-timed_out",
        "history-job-failed",
        "history-job-succeeded",
    ]
    assert payload["data"][0]["record_kind"] == "execution_job"
    assert payload["data"][0]["deletable"] is False
    assert payload["data"][-1]["record_kind"] == "call_history"
    assert payload["data"][-1]["deletable"] is True
    assert {item["status"] for item in payload["data"]} == {
        "passed",
        "failed",
        "error",
        "skipped",
    }

    filtered = client.get(
        "/api/v1/history",
        params={
            "status": "passed",
            "method": "GET",
            "url": "HEALTH",
            "project_id": project.id,
        },
    ).json()
    assert [item["id"] for item in filtered["data"]] == [
        "history-job-succeeded"
    ]

    stats = client.get(
        "/api/v1/history/stats",
        params={"project_id": project.id},
    ).json()["data"]
    assert stats == {
        "total": 5,
        "passed": 2,
        "failed": 1,
        "error": 1,
        "skipped": 1,
        "pass_rate": 40.0,
        "avg_duration": 2.1,
    }

    detail = client.get("/api/v1/history/history-job-succeeded")
    assert detail.status_code == 200, detail.text
    detail_data = detail.json()["data"]
    assert detail_data["id"] == "history-job-succeeded"
    assert detail_data["record_kind"] == "execution_job"
    assert detail_data["source"] == "api_case"
    assert detail_data["response_body"]["metrics"]["passed"] == 1

    assert client.delete("/api/v1/history/history-job-succeeded").status_code == 404
    assert db_session.get(ExecutionJob, "history-job-succeeded") is not None

    cleared = client.delete(
        "/api/v1/history",
        params={"project_id": project.id},
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["deleted_count"] == 1
    assert db_session.get(CallHistory, call_id) is None
    assert db_session.query(ExecutionJob).count() == 4


def test_history_execution_jobs_follow_project_scope(db_session):
    viewer = _user("history-viewer")
    other = _user("history-other")
    project_a = Project(id="history-project-a", name="Project A")
    project_b = Project(id="history-project-b", name="Project B")
    case_a = ApiTestCase(
        id="history-case-a",
        title="Visible",
        method="GET",
        url="https://example.test/a",
        project_id=project_a.id,
    )
    case_b = ApiTestCase(
        id="history-case-b",
        title="Hidden",
        method="GET",
        url="https://example.test/b",
        project_id=project_b.id,
    )
    db_session.add_all([viewer, other, project_a, project_b, case_a, case_b])
    db_session.flush()
    db_session.add(
        ProjectMember(
            project_id=project_a.id,
            user_id=viewer.id,
            role="viewer",
            created_by=other.id,
        )
    )
    db_session.add_all(
        [
            _job(
                job_id="history-visible-job",
                status="succeeded",
                project_id=project_a.id,
                created_by=other.id,
                resource_id=case_a.id,
                created_at=datetime(2026, 7, 17, 10, 0),
                duration=0.1,
            ),
            _job(
                job_id="history-hidden-job",
                status="failed",
                project_id=project_b.id,
                created_by=other.id,
                resource_id=case_b.id,
                created_at=datetime(2026, 7, 17, 11, 0),
                duration=0.2,
            ),
        ]
    )
    db_session.commit()

    current = {"user": viewer}
    with _client(db_session, current) as scoped_client:
        response = scoped_client.get("/api/v1/history")
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["data"]] == [
            "history-visible-job"
        ]
        assert scoped_client.get(
            "/api/v1/history/history-visible-job"
        ).status_code == 200
        assert scoped_client.get(
            "/api/v1/history/history-hidden-job"
        ).status_code == 404
        assert scoped_client.get(
            "/api/v1/history/stats"
        ).json()["data"]["total"] == 1
