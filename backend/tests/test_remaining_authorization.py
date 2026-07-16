"""Authorization coverage for notifications, reports, history, and CI/CD."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import get_db
from app.main import create_app
from app.models.call_history import CallHistory
from app.models.notification_channel import NotificationChannel
from app.models.notification_log import NotificationLog
from app.models.notification_rule import NotificationRule
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.test_case import TestCase as ApiTestCase
from app.models.test_result import TestResult as ORMTestResult
from app.models.test_run_summary import TestRunSummary as ORMTestRunSummary
from app.models.user import User
from app.models.webhook_config import WebhookConfig
from app.schemas.execution import ExecutionResult, ResponseData
from app.services.auth_service import get_current_user
from app.services.ci_cd_service import create_token


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


def _seed_scope(db_session):
    users = {
        "viewer": _user("remaining-viewer"),
        "tester": _user("remaining-tester"),
        "developer": _user("remaining-developer"),
        "admin": _user("remaining-admin"),
        "outsider": _user("remaining-outsider"),
        "other_admin": _user("remaining-other-admin"),
        "superuser": _user("remaining-superuser", superuser=True),
    }
    project_a = Project(id="remaining-project-a", name="Project A")
    project_b = Project(id="remaining-project-b", name="Project B")
    db_session.add_all([*users.values(), project_a, project_b])
    db_session.flush()
    db_session.add_all(
        [
            ProjectMember(
                project_id=project_a.id,
                user_id=users[role].id,
                role=role,
                created_by=users["admin"].id,
            )
            for role in ("viewer", "tester", "developer", "admin")
        ]
    )
    db_session.add(
        ProjectMember(
            project_id=project_b.id,
            user_id=users["other_admin"].id,
            role="admin",
            created_by=users["other_admin"].id,
        )
    )
    db_session.commit()
    return users, project_a, project_b


def _execution_result(case_id: str) -> ExecutionResult:
    return ExecutionResult(
        test_case_id=case_id,
        status="passed",
        duration=0.01,
        request=None,
        response=ResponseData(
            status_code=200,
            headers={},
            body={"ok": True},
            elapsed=0.01,
            text='{"ok": true}',
        ),
        assertion_results=[],
        extracted_variables=[],
        executed_at=datetime.now(),
    )


def test_notification_workspace_and_project_boundaries(db_session):
    users, project_a, project_b = _seed_scope(db_session)
    channel = NotificationChannel(
        id="remaining-channel",
        name="Workspace channel",
        type="slack",
        webhook_url="https://example.test/notify",
    )
    rules = [
        NotificationRule(
            id="remaining-rule-a",
            name="Rule A",
            channel_id=channel.id,
            event_type="test_run.completed",
            project_id=project_a.id,
        ),
        NotificationRule(
            id="remaining-rule-b",
            name="Rule B",
            channel_id=channel.id,
            event_type="test_run.completed",
            project_id=project_b.id,
        ),
        NotificationRule(
            id="remaining-rule-workspace",
            name="Workspace rule",
            channel_id=channel.id,
            event_type="test_run.failed",
            project_id=None,
        ),
    ]
    logs = [
        NotificationLog(
            id="remaining-log-a",
            channel_id=channel.id,
            channel_name=channel.name,
            project_id=project_a.id,
            event_type="test_run.completed",
            status="success",
        ),
        NotificationLog(
            id="remaining-log-b",
            channel_id=channel.id,
            channel_name=channel.name,
            project_id=project_b.id,
            event_type="test_run.completed",
            status="success",
        ),
        NotificationLog(
            id="remaining-log-workspace",
            channel_id=channel.id,
            channel_name=channel.name,
            project_id=None,
            event_type="test",
            status="success",
        ),
    ]
    db_session.add_all([channel, *rules, *logs])
    db_session.commit()
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        assert client.get("/api/v1/notifications/channels").status_code == 403

        response = client.get("/api/v1/notifications/rules")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["data"]} == {"remaining-rule-a"}
        response = client.get("/api/v1/notifications/logs")
        assert {item["id"] for item in response.json()["data"]} == {"remaining-log-a"}
        assert (
            client.get(
                "/api/v1/notifications/rules",
                params={"project_id": project_b.id},
            ).status_code
            == 403
        )

        current["user"] = users["developer"]
        response = client.post(
            "/api/v1/notifications/rules",
            json={
                "name": "Created rule",
                "channel_id": channel.id,
                "event_type": "test_run.failed",
                "project_id": project_a.id,
            },
        )
        assert response.status_code == 200, response.text
        created_rule_id = response.json()["data"]["id"]
        assert (
            client.post(
                "/api/v1/notifications/rules",
                json={
                    "name": "Workspace denied",
                    "channel_id": channel.id,
                    "event_type": "test_run.failed",
                },
            ).status_code
            == 403
        )
        assert client.delete(f"/api/v1/notifications/rules/{created_rule_id}").status_code == 403

        current["user"] = users["admin"]
        assert client.delete(f"/api/v1/notifications/rules/{created_rule_id}").status_code == 200

        current["user"] = users["outsider"]
        assert client.get("/api/v1/notifications/rules").json()["total"] == 0
        assert client.get("/api/v1/notifications/logs").json()["total"] == 0

        current["user"] = users["superuser"]
        assert client.get("/api/v1/notifications/channels").status_code == 200
        assert client.get("/api/v1/notifications/rules").json()["total"] == 3
        assert client.get("/api/v1/notifications/logs").json()["total"] == 3


def test_reports_and_history_are_scoped_by_project_or_creator(db_session):
    users, project_a, project_b = _seed_scope(db_session)
    case_a = ApiTestCase(
        id="remaining-case-a",
        title="Case A",
        method="GET",
        url="https://example.test/a",
        project_id=project_a.id,
    )
    case_b = ApiTestCase(
        id="remaining-case-b",
        title="Case B",
        method="GET",
        url="https://example.test/b",
        project_id=project_b.id,
    )
    summaries = [
        ORMTestRunSummary(
            run_id="remaining-run-a",
            project_id=project_a.id,
            created_by=users["other_admin"].id,
            total=1,
            passed=1,
        ),
        ORMTestRunSummary(
            run_id="remaining-run-b",
            project_id=project_b.id,
            created_by=users["other_admin"].id,
            total=1,
            failed=1,
        ),
        ORMTestRunSummary(
            run_id="remaining-run-owned",
            project_id=None,
            created_by=users["viewer"].id,
            total=1,
            passed=1,
        ),
        ORMTestRunSummary(
            run_id="remaining-run-other",
            project_id=None,
            created_by=users["other_admin"].id,
            total=1,
            passed=1,
        ),
    ]
    results = [
        ORMTestResult(
            run_id="remaining-run-a",
            test_case_id=case_a.id,
            status="passed",
            duration=0.1,
            executed_at=datetime(2026, 7, 15, 10, 0),
        ),
        ORMTestResult(
            run_id="remaining-run-b",
            test_case_id=case_b.id,
            status="failed",
            duration=0.1,
            executed_at=datetime(2026, 7, 15, 10, 0),
        ),
        ORMTestResult(
            run_id="remaining-run-owned",
            test_case_id=case_a.id,
            status="passed",
            duration=0.1,
            executed_at=datetime(2026, 7, 15, 10, 0),
        ),
        ORMTestResult(
            run_id="remaining-run-other",
            test_case_id=case_b.id,
            status="passed",
            duration=0.1,
            executed_at=datetime(2026, 7, 15, 10, 0),
        ),
    ]
    histories = [
        CallHistory(
            id="remaining-history-a",
            method="GET",
            url="https://example.test/a",
            status="passed",
            duration=0.1,
            project_id=project_a.id,
            created_by=users["other_admin"].id,
        ),
        CallHistory(
            id="remaining-history-b",
            method="GET",
            url="https://example.test/b",
            status="failed",
            duration=0.1,
            project_id=project_b.id,
            created_by=users["other_admin"].id,
        ),
        CallHistory(
            id="remaining-history-owned",
            method="GET",
            url="https://example.test/owned",
            status="passed",
            duration=0.1,
            project_id=None,
            created_by=users["viewer"].id,
        ),
        CallHistory(
            id="remaining-history-other",
            method="GET",
            url="https://example.test/other",
            status="passed",
            duration=0.1,
            project_id=None,
            created_by=users["other_admin"].id,
        ),
    ]
    db_session.add_all([case_a, case_b, *summaries, *results, *histories])
    db_session.commit()
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        response = client.get("/api/v1/reports/runs")
        assert {item["run_id"] for item in response.json()["data"]} == {
            "remaining-run-a",
            "remaining-run-owned",
        }
        assert client.get("/api/v1/reports/runs/remaining-run-b/results").status_code == 403
        assert client.get("/api/v1/reports/runs/remaining-run-owned/summary").status_code == 200
        response = client.get(
            "/api/v1/reports/trends",
            params={
                "start": "2026-07-15T00:00:00",
                "end": "2026-07-16T00:00:00",
            },
        )
        assert response.json()["data"][0]["total"] == 2

        response = client.get("/api/v1/history")
        assert {item["id"] for item in response.json()["data"]} == {
            "remaining-history-a",
            "remaining-history-owned",
        }
        assert client.get("/api/v1/history/stats").json()["data"]["total"] == 2
        assert client.get("/api/v1/history/remaining-history-b").status_code == 403
        assert client.delete("/api/v1/history/remaining-history-a").status_code == 403
        assert client.delete("/api/v1/history/remaining-history-owned").status_code == 200

        current["user"] = users["admin"]
        response = client.delete(
            "/api/v1/history",
            params={"project_id": project_a.id},
        )
        assert response.status_code == 200
        assert response.json()["data"]["deleted_count"] == 1
        assert db_session.get(CallHistory, "remaining-history-b") is not None

        current["user"] = users["superuser"]
        assert client.get("/api/v1/reports/runs").json()["data"]
        assert client.get("/api/v1/history").json()["total"] == 2


def test_ci_webhook_role_matrix(db_session):
    users, project_a, project_b = _seed_scope(db_session)
    configs = [
        WebhookConfig(
            id="remaining-webhook-a",
            name="Webhook A",
            url="https://example.test/a",
            events=["test_run.completed"],
            project_id=project_a.id,
        ),
        WebhookConfig(
            id="remaining-webhook-b",
            name="Webhook B",
            url="https://example.test/b",
            events=["test_run.completed"],
            project_id=project_b.id,
        ),
        WebhookConfig(
            id="remaining-webhook-workspace",
            name="Workspace webhook",
            url="https://example.test/workspace",
            events=["test_run.completed"],
            project_id=None,
        ),
    ]
    db_session.add_all(configs)
    db_session.commit()
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        response = client.get("/api/v1/ci/webhooks")
        assert {item["id"] for item in response.json()["data"]} == {"remaining-webhook-a"}
        assert client.get("/api/v1/ci/webhooks/remaining-webhook-b").status_code == 403
        assert (
            client.post(
                "/api/v1/ci/webhooks",
                json={
                    "name": "Denied",
                    "url": "https://example.test/denied",
                    "project_id": project_a.id,
                },
            ).status_code
            == 403
        )

        current["user"] = users["developer"]
        response = client.post(
            "/api/v1/ci/webhooks",
            json={
                "name": "Created",
                "url": "https://example.test/created",
                "events": ["test_run.completed"],
                "project_id": project_a.id,
            },
        )
        assert response.status_code == 200, response.text
        created_id = response.json()["data"]["id"]
        assert (
            client.put(
                f"/api/v1/ci/webhooks/{created_id}",
                json={"name": "Updated"},
            ).status_code
            == 200
        )
        assert client.delete(f"/api/v1/ci/webhooks/{created_id}").status_code == 403

        current["user"] = users["viewer"]
        assert client.post("/api/v1/ci/webhooks/remaining-webhook-a/test").status_code == 403
        current["user"] = users["tester"]
        with patch("app.api.v1.ci_cd.send_webhook") as mock_send:
            mock_send.return_value = [
                {
                    "webhook_id": "remaining-webhook-a",
                    "success": True,
                    "status_code": 200,
                }
            ]
            assert client.post("/api/v1/ci/webhooks/remaining-webhook-a/test").status_code == 200

        current["user"] = users["admin"]
        assert client.delete(f"/api/v1/ci/webhooks/{created_id}").status_code == 200

        current["user"] = users["superuser"]
        assert len(client.get("/api/v1/ci/webhooks").json()["data"]) == 3
        assert (
            client.post(
                "/api/v1/ci/webhooks",
                json={
                    "name": "Workspace",
                    "url": "https://example.test/new-workspace",
                },
            ).status_code
            == 200
        )


def test_ci_token_project_binding_and_run_status(db_session):
    users, project_a, project_b = _seed_scope(db_session)
    case_a = ApiTestCase(
        id="remaining-ci-case-a",
        title="CI Case A",
        method="GET",
        url="https://example.test/a",
        project_id=project_a.id,
    )
    case_b = ApiTestCase(
        id="remaining-ci-case-b",
        title="CI Case B",
        method="GET",
        url="https://example.test/b",
        project_id=project_b.id,
    )
    legacy_case = ApiTestCase(
        id="remaining-ci-case-legacy",
        title="CI Legacy Case",
        method="GET",
        url="https://example.test/legacy",
        project_id=None,
    )
    db_session.add_all([case_a, case_b, legacy_case])
    db_session.commit()

    _, tester_token = create_token(
        db_session,
        name="tester-token",
        scopes=["test-cases:execute"],
        user_id=users["tester"].id,
    )
    _, viewer_token = create_token(
        db_session,
        name="viewer-token",
        scopes=["test-cases:execute"],
        user_id=users["viewer"].id,
    )
    _, legacy_token = create_token(
        db_session,
        name="legacy-token",
        scopes=["test-cases:execute"],
    )
    _, superuser_token = create_token(
        db_session,
        name="superuser-token",
        scopes=["test-cases:execute"],
        user_id=users["superuser"].id,
    )
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        with (
            patch("app.services.ci_cd_service._ci_executor") as executor,
            patch("app.api.v1.ci_cd._notify_webhooks"),
        ):
            executor.execute.side_effect = lambda **kwargs: _execution_result(kwargs["test_case_id"])
            response = client.post(
                "/api/v1/ci/trigger",
                json={"case_ids": [case_a.id]},
                headers={"X-API-Key": tester_token},
            )
            assert response.status_code == 200, response.text
            run_id = response.json()["data"]["run_id"]

            assert (
                client.post(
                    "/api/v1/ci/trigger",
                    json={"case_ids": [case_a.id]},
                    headers={"X-API-Key": viewer_token},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/ci/trigger",
                    json={"case_ids": [case_b.id]},
                    headers={"X-API-Key": tester_token},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/ci/trigger",
                    json={"case_ids": [case_a.id]},
                    headers={"X-API-Key": legacy_token},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/ci/trigger",
                    json={"case_ids": [legacy_case.id]},
                    headers={"X-API-Key": legacy_token},
                ).status_code
                == 200
            )
            assert (
                client.post(
                    "/api/v1/ci/trigger",
                    json={"case_ids": [case_b.id]},
                    headers={"X-API-Key": superuser_token},
                ).status_code
                == 200
            )

        summary = db_session.execute(select(ORMTestRunSummary).where(ORMTestRunSummary.run_id == run_id)).scalar_one()
        assert summary.project_id == project_a.id
        assert summary.created_by == users["tester"].id

        assert client.get(f"/api/v1/ci/runs/{run_id}/status").status_code == 200
        current["user"] = users["outsider"]
        assert client.get(f"/api/v1/ci/runs/{run_id}/status").status_code == 403
