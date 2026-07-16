"""Project membership and task resource isolation tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import create_app
from app.models.project_member import ProjectMember
from app.models.ui_test_case import UiTestCase
from app.models.user import User
from app.services.auth_service import get_current_user


def _user(user_id: str, username: str, *, superuser: bool = False) -> User:
    return User(
        id=user_id,
        username=username,
        email=f"{username}@test.local",
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


def test_project_membership_scopes_crud(db_session):
    owner = _user("owner-id", "owner")
    viewer = _user("viewer-id", "viewer")
    outsider = _user("outsider-id", "outsider")
    db_session.add_all([owner, viewer, outsider])
    db_session.commit()
    current = {"user": owner}

    with _client(db_session, current) as client:
        response = client.post(
            "/api/v1/projects",
            json={"name": "Scoped project", "code": "SCOPED"},
        )
        assert response.status_code == 200
        project_id = response.json()["data"]["id"]

        membership = db_session.get(ProjectMember, (project_id, owner.id))
        assert membership.role == "owner"

        response = client.post(
            f"/api/v1/projects/{project_id}/members",
            json={"user_id": viewer.id, "role": "viewer"},
        )
        assert response.status_code == 200

        current["user"] = viewer
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 200
        assert (
            client.put(
                f"/api/v1/projects/{project_id}",
                json={"name": "blocked"},
            ).status_code
            == 403
        )

        current["user"] = outsider
        response = client.get("/api/v1/projects")
        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 403


def test_job_access_uses_resource_project(db_session):
    owner = _user("job-owner-id", "job-owner")
    viewer = _user("job-viewer-id", "job-viewer")
    outsider = _user("job-outsider-id", "job-outsider")
    db_session.add_all([owner, viewer, outsider])
    db_session.commit()
    current = {"user": owner}

    with _client(db_session, current) as client:
        project_response = client.post(
            "/api/v1/projects",
            json={"name": "Job project"},
        )
        project_id = project_response.json()["data"]["id"]
        client.post(
            f"/api/v1/projects/{project_id}/members",
            json={"user_id": viewer.id, "role": "viewer"},
        )

        ui_case = UiTestCase(
            title="Placeholder UI case",
            url="https://example.test",
            project_id=project_id,
            steps=[],
        )
        db_session.add(ui_case)
        db_session.commit()

        response = client.post(
            "/api/v1/jobs",
            json={
                "job_type": "ui_case",
                "resource_id": ui_case.id,
            },
        )
        assert response.status_code == 200
        job_id = response.json()["data"]["id"]
        assert response.json()["data"]["project_id"] == project_id

        current["user"] = viewer
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 200
        assert (
            client.post(
                "/api/v1/jobs",
                json={"job_type": "ui_case", "resource_id": ui_case.id},
            ).status_code
            == 403
        )
        assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 403

        current["user"] = outsider
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 403
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
        assert response.json()["total"] == 0
