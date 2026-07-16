"""Project isolation and role checks for test plans."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import create_app
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.test_case import TestCase as ApiTestCase
from app.models.test_plan import TestPlan as PlanModel
from app.models.user import User
from app.services.auth_service import get_current_user

BASE = "/api/v1/test-plans"


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


def _seed_projects_and_roles(db_session):
    users = {
        "viewer": _user("plan-viewer"),
        "tester": _user("plan-tester"),
        "developer": _user("plan-developer"),
        "admin": _user("plan-admin"),
        "outsider": _user("plan-outsider"),
        "project_b_admin": _user("plan-project-b-admin"),
        "superuser": _user("plan-superuser", superuser=True),
    }
    project_a = Project(id="plan-project-a", name="Plan project A")
    project_b = Project(id="plan-project-b", name="Plan project B")
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
            user_id=users["project_b_admin"].id,
            role="admin",
            created_by=users["project_b_admin"].id,
        )
    )
    db_session.commit()
    return users, project_a, project_b


def test_empty_plan_uses_project_role_matrix(db_session):
    users, project_a, _ = _seed_projects_and_roles(db_session)
    current = {"user": users["developer"]}

    with _client(db_session, current) as client:
        response = client.post(
            BASE,
            json={"name": "Empty plan", "project_id": project_a.id},
        )
        assert response.status_code == 200, response.text
        plan = response.json()["data"]
        plan_path = f"{BASE}/{plan['id']}"
        assert plan["project_id"] == project_a.id
        assert plan["created_by"] == users["developer"].id
        assert plan["items"] == []

        current["user"] = users["viewer"]
        assert client.get(plan_path).status_code == 200
        assert client.put(plan_path, json={"name": "blocked"}).status_code == 403
        assert client.post(f"{plan_path}/execute-chain").status_code == 403
        assert client.delete(plan_path).status_code == 403

        current["user"] = users["tester"]
        execute = client.post(f"{plan_path}/execute-chain")
        assert execute.status_code == 200
        assert execute.json()["data"]["total"] == 0
        assert client.put(plan_path, json={"name": "blocked"}).status_code == 403

        current["user"] = users["developer"]
        assert client.put(plan_path, json={"name": "Updated plan"}).status_code == 200
        assert client.delete(plan_path).status_code == 403

        current["user"] = users["superuser"]
        response = client.put(plan_path, json={"project_id": None})
        assert response.status_code == 422
        assert client.get(plan_path).json()["data"]["project_id"] == project_a.id

        current["user"] = users["admin"]
        assert client.delete(plan_path).status_code == 200
        assert client.get(plan_path).status_code == 404


def test_cross_project_plan_operations_are_forbidden(db_session):
    users, project_a, project_b = _seed_projects_and_roles(db_session)
    plan_a = PlanModel(
        id="plan-a",
        name="Plan A",
        project_id=project_a.id,
        created_by=users["admin"].id,
    )
    plan_b = PlanModel(
        id="plan-b",
        name="Plan B",
        project_id=project_b.id,
        created_by=users["project_b_admin"].id,
    )
    db_session.add_all([plan_a, plan_b])
    db_session.commit()
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        response = client.get(BASE)
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["data"]} == {plan_a.id}

        assert (
            client.get(BASE, params={"project_id": project_b.id}).status_code
            == 403
        )
        foreign_path = f"{BASE}/{plan_b.id}"
        assert client.get(foreign_path).status_code == 403
        assert client.put(foreign_path, json={"name": "blocked"}).status_code == 403
        assert client.delete(foreign_path).status_code == 403
        assert client.post(f"{foreign_path}/execute-chain").status_code == 403
        assert client.get(f"{BASE}/missing-plan").status_code == 404

        current["user"] = users["developer"]
        assert (
            client.post(
                BASE,
                json={"name": "Foreign plan", "project_id": project_b.id},
            ).status_code
            == 403
        )

        current["user"] = users["admin"]
        assert (
            client.put(
                f"{BASE}/{plan_a.id}",
                json={"project_id": project_b.id},
            ).status_code
            == 403
        )


def test_plan_items_must_match_plan_project(db_session):
    users, project_a, project_b = _seed_projects_and_roles(db_session)
    plan = PlanModel(
        id="plan-item-scope",
        name="Scoped plan",
        project_id=project_a.id,
        created_by=users["admin"].id,
    )
    case_a = ApiTestCase(
        id="plan-case-a",
        title="Case A",
        method="GET",
        url="https://example.test/a",
        project_id=project_a.id,
    )
    case_b = ApiTestCase(
        id="plan-case-b",
        title="Case B",
        method="GET",
        url="https://example.test/b",
        project_id=project_b.id,
    )
    db_session.add_all([plan, case_a, case_b])
    db_session.commit()
    current = {"user": users["admin"]}

    with _client(db_session, current) as client:
        assert (
            client.post(
                f"{BASE}/{plan.id}/items",
                json={"test_case_id": case_a.id},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"{BASE}/{plan.id}/items",
                json={"test_case_id": case_b.id},
            ).status_code
            == 403
        )

        current["user"] = users["superuser"]
        assert (
            client.post(
                f"{BASE}/{plan.id}/items",
                json={"test_case_id": case_b.id},
            ).status_code
            == 422
        )
        assert (
            client.put(
                f"{BASE}/{plan.id}",
                json={"project_id": project_b.id},
            ).status_code
            == 422
        )
