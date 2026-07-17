"""Focused tests for unified API coverage reporting."""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import create_app
from app.models.execution_job import ExecutionJob
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.test_case import TestCase as ApiTestCase
from app.models.test_result import TestResult as ORMTestResult
from app.models.test_run_summary import TestRunSummary as ORMTestRunSummary
from app.models.user import User
from app.services.auth_service import get_current_user


def _user(user_id: str, *, superuser: bool = False) -> User:
    return User(
        id=user_id,
        username=user_id,
        email=f"{user_id}@test.local",
        hashed_password="not-used",
        is_active=True,
        is_superuser=superuser,
    )


def _client(
    db_session,
    current: dict[str, User] | None = None,
) -> TestClient:
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    if current is not None:
        app.dependency_overrides[get_current_user] = lambda: current["user"]
    return TestClient(app)


def _case(
    case_id: str,
    *,
    method: str,
    url: str,
    group_path: str | None,
    project_id: str | None,
) -> ApiTestCase:
    return ApiTestCase(
        id=case_id,
        title=case_id,
        method=method,
        url=url,
        group_path=group_path,
        project_id=project_id,
    )


def test_coverage_requires_authentication(db_session):
    with _client(db_session) as client:
        response = client.get("/api/v1/coverage")

    assert response.status_code == 401


def test_coverage_unifies_jobs_and_legacy_results_with_access_scope(db_session):
    viewer = _user("coverage-viewer")
    other = _user("coverage-other")
    superuser = _user("coverage-superuser", superuser=True)
    project_a = Project(id="coverage-project-a", name="Coverage A")
    project_b = Project(id="coverage-project-b", name="Coverage B")
    db_session.add_all(
        [viewer, other, superuser, project_a, project_b]
    )
    db_session.flush()
    db_session.add(
        ProjectMember(
            project_id=project_a.id,
            user_id=viewer.id,
            role="viewer",
            created_by=other.id,
        )
    )

    case_legacy = _case(
        "coverage-case-legacy",
        method="GET",
        url="/legacy",
        group_path="Core",
        project_id=project_a.id,
    )
    case_job = _case(
        "coverage-case-job",
        method="POST",
        url="/job",
        group_path="Core",
        project_id=project_a.id,
    )
    case_uncovered = _case(
        "coverage-case-uncovered",
        method="DELETE",
        url="/uncovered",
        group_path="Admin",
        project_id=project_a.id,
    )
    case_owned_legacy = _case(
        "coverage-case-owned-legacy",
        method="PATCH",
        url="/owned-legacy",
        group_path=None,
        project_id=None,
    )
    case_other_legacy = _case(
        "coverage-case-other-legacy",
        method="PUT",
        url="/other-legacy",
        group_path=None,
        project_id=None,
    )
    case_hidden = _case(
        "coverage-case-hidden",
        method="GET",
        url="/hidden",
        group_path="Hidden",
        project_id=project_b.id,
    )
    db_session.add_all(
        [
            case_legacy,
            case_job,
            case_uncovered,
            case_owned_legacy,
            case_other_legacy,
            case_hidden,
        ]
    )

    legacy_runs = [
        ORMTestRunSummary(
            run_id="coverage-run-legacy",
            project_id=project_a.id,
            created_by=other.id,
            total=1,
            passed=1,
            created_at=datetime(2026, 7, 10, 10, 0),
        ),
        ORMTestRunSummary(
            run_id="coverage-run-owned",
            project_id=None,
            created_by=viewer.id,
            total=1,
            passed=1,
            created_at=datetime(2026, 7, 11, 10, 0),
        ),
        ORMTestRunSummary(
            run_id="coverage-run-other",
            project_id=None,
            created_by=other.id,
            total=1,
            passed=1,
            created_at=datetime(2026, 7, 12, 10, 0),
        ),
        ORMTestRunSummary(
            run_id="coverage-run-hidden",
            project_id=project_b.id,
            created_by=other.id,
            total=1,
            failed=1,
            created_at=datetime(2026, 7, 13, 10, 0),
        ),
        ORMTestRunSummary(
            run_id="coverage-run-shared",
            project_id=project_a.id,
            created_by=other.id,
            total=99,
            passed=99,
            created_at=datetime(2026, 7, 16, 10, 0),
        ),
    ]
    legacy_results = [
        ORMTestResult(
            run_id="coverage-run-legacy",
            test_case_id=case_legacy.id,
            status="passed",
        ),
        ORMTestResult(
            run_id="coverage-run-owned",
            test_case_id=case_owned_legacy.id,
            status="passed",
        ),
        ORMTestResult(
            run_id="coverage-run-other",
            test_case_id=case_other_legacy.id,
            status="passed",
        ),
        ORMTestResult(
            run_id="coverage-run-hidden",
            test_case_id=case_hidden.id,
            status="failed",
        ),
    ]
    jobs = [
        ExecutionJob(
            id="coverage-run-shared",
            job_type="api_case",
            resource_id=case_job.id,
            project_id=project_a.id,
            status="failed",
            created_by=other.id,
            config={
                "_result_metrics": {
                    "total": 2,
                    "passed": 1,
                    "failed": 1,
                    "error": 0,
                    "skipped": 0,
                    "duration": 0.25,
                }
            },
            started_at=datetime(2026, 7, 14, 10, 0),
            finished_at=datetime(2026, 7, 14, 10, 1),
            created_at=datetime(2026, 7, 14, 10, 0),
        ),
        ExecutionJob(
            id="coverage-job-running",
            job_type="api_case",
            resource_id=case_uncovered.id,
            project_id=project_a.id,
            status="running",
            created_by=viewer.id,
            created_at=datetime(2026, 7, 15, 10, 0),
        ),
        ExecutionJob(
            id="coverage-job-hidden",
            job_type="api_case",
            resource_id=case_hidden.id,
            project_id=project_b.id,
            status="succeeded",
            created_by=other.id,
            created_at=datetime(2026, 7, 15, 11, 0),
        ),
    ]
    db_session.add_all([*legacy_runs, *legacy_results, *jobs])
    db_session.commit()

    current = {"user": viewer}
    with _client(db_session, current) as client:
        response = client.get("/api/v1/coverage")
        assert response.status_code == 200, response.text
        data = response.json()["data"]

        assert data["total_endpoints"] == 4
        assert data["covered"] == 3
        assert data["uncovered"] == 1
        assert data["coverage_rate"] == 75.0
        assert {
            item["method"]: (item["total"], item["covered"])
            for item in data["by_method"]
        } == {
            "DELETE": (1, 0),
            "GET": (1, 1),
            "PATCH": (1, 1),
            "POST": (1, 1),
        }
        assert {
            item["group_path"]: (item["total"], item["covered"])
            for item in data["by_group"]
        } == {
            "Admin": (1, 0),
            "Core": (2, 2),
            "未分组": (1, 1),
        }

        recent_runs = data["recent_runs"]
        assert [item["run_id"] for item in recent_runs] == [
            "coverage-run-legacy",
            "coverage-run-owned",
            "coverage-run-shared",
        ]
        shared = next(
            item
            for item in recent_runs
            if item["run_id"] == "coverage-run-shared"
        )
        assert shared["total"] == 2
        assert shared["passed"] == 1
        assert shared["created_at"] == "07-14 10:00"

        denied = client.get(
            "/api/v1/coverage",
            params={"project_id": project_b.id},
        )
        assert denied.status_code == 403

        project_response = client.get(
            "/api/v1/coverage",
            params={"project_id": project_a.id},
        )
        assert project_response.status_code == 200
        project_data = project_response.json()["data"]
        assert project_data["total_endpoints"] == 3
        assert project_data["covered"] == 2
        assert {
            item["run_id"]
            for item in project_data["recent_runs"]
        } == {
            "coverage-run-legacy",
            "coverage-run-shared",
        }

        current["user"] = superuser
        super_data = client.get("/api/v1/coverage").json()["data"]
        assert super_data["total_endpoints"] == 6
        assert super_data["covered"] == 5
        assert {
            item["run_id"]
            for item in super_data["recent_runs"]
        } == {
            "coverage-run-legacy",
            "coverage-run-owned",
            "coverage-run-other",
            "coverage-run-hidden",
            "coverage-run-shared",
            "coverage-job-hidden",
        }
