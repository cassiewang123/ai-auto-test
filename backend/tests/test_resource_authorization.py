"""Project-level authorization tests for business resources."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.v1 import ui_test_cases as ui_test_cases_api
from app.database import get_db
from app.main import create_app
from app.models.contract import ContractVersion
from app.models.defect_integration import DefectTicket
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.quality_gate import QualityGate
from app.models.test_case import TestCase as ApiTestCase
from app.models.ui_test_case import UiTestCase
from app.models.user import User
from app.models.workflow import WorkflowDefinition
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
        "viewer": _user("resource-viewer"),
        "tester": _user("resource-tester"),
        "developer": _user("resource-developer"),
        "admin": _user("resource-admin"),
        "outsider": _user("resource-outsider"),
        "other": _user("resource-other"),
        "superuser": _user("resource-superuser", superuser=True),
    }
    project_a = Project(id="resource-project-a", name="Project A")
    project_b = Project(id="resource-project-b", name="Project B")
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
    db_session.commit()
    return users, project_a, project_b


def _api_case(case_id: str, project_id: str | None) -> ApiTestCase:
    return ApiTestCase(
        id=case_id,
        title=case_id,
        method="GET",
        url="https://example.test/ping",
        project_id=project_id,
    )


def _ui_case(case_id: str, project_id: str | None) -> UiTestCase:
    return UiTestCase(
        id=case_id,
        title=case_id,
        url="https://example.test",
        steps=[],
        project_id=project_id,
    )


def test_member_lists_only_include_accessible_project_resources(db_session):
    users, project_a, project_b = _seed_projects_and_roles(db_session)
    resources = [
        WorkflowDefinition(
            id="workflow-a",
            name="Workflow A",
            project_id=project_a.id,
            created_by=users["other"].id,
        ),
        WorkflowDefinition(
            id="workflow-b",
            name="Workflow B",
            project_id=project_b.id,
            created_by=users["other"].id,
        ),
        WorkflowDefinition(
            id="workflow-owned-legacy",
            name="Owned legacy workflow",
            project_id=None,
            created_by=users["viewer"].id,
        ),
        WorkflowDefinition(
            id="workflow-other-legacy",
            name="Other legacy workflow",
            project_id=None,
            created_by=users["other"].id,
        ),
        ContractVersion(
            id="contract-version-a",
            contract_id="contract-a",
            name="Contract A",
            version=1,
            project_id=project_a.id,
            status="active",
            created_by=users["other"].id,
        ),
        ContractVersion(
            id="contract-version-b",
            contract_id="contract-b",
            name="Contract B",
            version=1,
            project_id=project_b.id,
            status="active",
            created_by=users["other"].id,
        ),
        QualityGate(
            id="gate-a",
            name="Gate A",
            project_id=project_a.id,
            rules="[]",
        ),
        QualityGate(
            id="gate-b",
            name="Gate B",
            project_id=project_b.id,
            rules="[]",
        ),
        DefectTicket(
            id="defect-a",
            title="Defect A",
            project_id=project_a.id,
            created_by=users["other"].id,
        ),
        DefectTicket(
            id="defect-b",
            title="Defect B",
            project_id=project_b.id,
            created_by=users["other"].id,
        ),
        DefectTicket(
            id="defect-owned-legacy",
            title="Owned legacy defect",
            project_id=None,
            created_by=users["viewer"].id,
        ),
        _api_case("api-case-a", project_a.id),
        _api_case("api-case-b", project_b.id),
        _ui_case("ui-case-a", project_a.id),
        _ui_case("ui-case-b", project_b.id),
    ]
    db_session.add_all(resources)
    db_session.commit()
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        expected_ids = {
            "/api/v1/workflows": {"workflow-a", "workflow-owned-legacy"},
            "/api/v1/contracts": {"contract-version-a"},
            "/api/v1/quality-gates": {"gate-a"},
            "/api/v1/defects": {"defect-a", "defect-owned-legacy"},
            "/api/v1/test-cases": {"api-case-a"},
            "/api/v1/ui-test-cases": {"ui-case-a"},
        }
        for path, expected in expected_ids.items():
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
            assert {item["id"] for item in response.json()["data"]} == expected
            assert response.json()["total"] == len(expected)

        for path in expected_ids:
            response = client.get(path, params={"project_id": project_b.id})
            assert response.status_code == 403, (path, response.text)


def test_workflow_role_matrix_and_id_responses(db_session):
    users, project_a, _ = _seed_projects_and_roles(db_session)
    workflow = WorkflowDefinition(
        id="workflow-role-matrix",
        name="Role matrix",
        project_id=project_a.id,
        nodes=json.dumps([]),
        edges=json.dumps([]),
        status="published",
        created_by=users["admin"].id,
    )
    db_session.add(workflow)
    db_session.commit()
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        path = f"/api/v1/workflows/{workflow.id}"
        assert client.get(path).status_code == 200
        assert client.put(path, json={"name": "blocked"}).status_code == 403
        assert client.post(f"{path}/run", json={}).status_code == 403
        assert client.delete(path).status_code == 403

        current["user"] = users["tester"]
        assert client.post(f"{path}/run", json={}).status_code == 200
        assert client.put(path, json={"name": "blocked"}).status_code == 403

        current["user"] = users["developer"]
        assert client.put(path, json={"name": "Updated"}).status_code == 200
        assert client.post(f"{path}/publish").status_code == 403
        assert client.delete(path).status_code == 403
        assert (
            client.post(
                "/api/v1/workflows",
                json={"name": "Created", "project_id": project_a.id},
            ).status_code
            == 200
        )

        current["user"] = users["admin"]
        assert client.post(f"{path}/publish").status_code == 200

        current["user"] = users["outsider"]
        assert client.get(path).status_code == 403
        assert client.get("/api/v1/workflows/missing-workflow").status_code == 404


def test_contract_gate_and_defect_operation_roles(db_session):
    users, project_a, _ = _seed_projects_and_roles(db_session)
    contract = ContractVersion(
        id="contract-role-version",
        contract_id="contract-role",
        name="Role contract",
        version=1,
        openapi_spec=json.dumps(
            {
                "paths": {
                    "/ping": {
                        "get": {
                            "responses": {
                                "200": {"description": "ok"},
                            }
                        }
                    }
                }
            }
        ),
        project_id=project_a.id,
        status="active",
        created_by=users["admin"].id,
    )
    gate = QualityGate(
        id="gate-role",
        name="Role gate",
        project_id=project_a.id,
        rules=json.dumps(
            [{"metric": "pass_rate", "op": ">=", "threshold": 0.9}]
        ),
    )
    defect = DefectTicket(
        id="defect-role",
        title="Role defect",
        project_id=project_a.id,
        external_system="jira",
        external_id="BUG-1",
        created_by=users["admin"].id,
    )
    db_session.add_all([contract, gate, defect])
    db_session.commit()
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        contract_path = f"/api/v1/contracts/{contract.contract_id}"
        assert client.get(f"{contract_path}/versions").status_code == 200
        assert (
            client.post(
                f"{contract_path}/validate",
                json={"method": "GET", "path": "/ping", "status_code": 200},
            ).status_code
            == 403
        )

        current["user"] = users["tester"]
        assert (
            client.post(
                f"{contract_path}/validate",
                json={"method": "GET", "path": "/ping", "status_code": 200},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/quality-gates/{gate.id}/evaluate",
                json={"metrics": {"pass_rate": 1.0}},
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v1/quality-gates/{gate.id}",
                json={"name": "blocked"},
            ).status_code
            == 403
        )

        current["user"] = users["developer"]
        assert (
            client.post(
                f"{contract_path}/versions",
                json={"openapi_spec": {"paths": {}}},
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v1/quality-gates/{gate.id}",
                json={"name": "Updated gate"},
            ).status_code
            == 200
        )
        assert (
            client.delete(f"/api/v1/quality-gates/{gate.id}").status_code
            == 403
        )
        assert (
            client.put(
                f"/api/v1/defects/{defect.id}",
                json={"status": "in_progress"},
            ).status_code
            == 200
        )
        assert client.post(f"/api/v1/defects/{defect.id}/sync").status_code == 403

        current["user"] = users["admin"]
        assert client.post(f"/api/v1/defects/{defect.id}/sync").status_code == 200
        assert client.delete(f"/api/v1/quality-gates/{gate.id}").status_code == 200

        current["user"] = users["outsider"]
        assert client.get(f"/api/v1/defects/{defect.id}").status_code == 403
        assert (
            client.get("/api/v1/defects/missing-defect").status_code == 404
        )


def test_api_and_ui_case_isolation_and_roles(db_session, monkeypatch):
    users, project_a, project_b = _seed_projects_and_roles(db_session)
    api_case = _api_case("api-case-role", project_a.id)
    foreign_api_case = _api_case("api-case-foreign", project_b.id)
    ui_case = _ui_case("ui-case-role", project_a.id)
    foreign_ui_case = _ui_case("ui-case-foreign", project_b.id)
    db_session.add_all(
        [api_case, foreign_api_case, ui_case, foreign_ui_case]
    )
    db_session.commit()
    current = {"user": users["viewer"]}

    result = {
        "status": "passed",
        "total_steps": 0,
        "passed_steps": 0,
        "failed_steps": 0,
        "error": None,
        "steps": [],
        "screenshots": [],
        "final_url": ui_case.url,
    }

    def fake_execute_ui_case(**_kwargs):
        return result, [], 1

    monkeypatch.setattr(
        "app.api.v1.ui_test_cases.execute_ui_case",
        fake_execute_ui_case,
    )

    with _client(db_session, current) as client:
        api_path = f"/api/v1/test-cases/{api_case.id}"
        ui_path = f"/api/v1/ui-test-cases/{ui_case.id}"
        assert client.get(api_path).status_code == 200
        assert client.get(ui_path).status_code == 200
        assert client.get(f"/api/v1/test-cases/{foreign_api_case.id}").status_code == 403
        assert client.get(f"/api/v1/ui-test-cases/{foreign_ui_case.id}").status_code == 403
        assert client.put(api_path, json={"title": "blocked"}).status_code == 403
        assert client.post(f"{ui_path}/run").status_code == 403

        current["user"] = users["tester"]
        assert client.post(f"{ui_path}/run").status_code == 200
        assert client.put(api_path, json={"title": "blocked"}).status_code == 403

        current["user"] = users["developer"]
        assert client.put(api_path, json={"title": "Updated API"}).status_code == 200
        assert client.put(ui_path, json={"title": "Updated UI"}).status_code == 200
        assert (
            client.post(
                "/api/v1/test-cases",
                json={
                    "title": "Created API",
                    "method": "GET",
                    "url": "https://example.test",
                    "project_id": project_a.id,
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/ui-test-cases",
                json={
                    "title": "Created UI",
                    "url": "https://example.test",
                    "project_id": project_a.id,
                },
            ).status_code
            == 200
        )
        assert client.delete(api_path).status_code == 403
        assert client.delete(ui_path).status_code == 403

        current["user"] = users["admin"]
        assert client.delete(api_path).status_code == 200
        assert client.delete(ui_path).status_code == 200


def test_unscoped_legacy_resource_requires_creator_or_superuser(db_session):
    users, _, _ = _seed_projects_and_roles(db_session)
    owned = WorkflowDefinition(
        id="legacy-owned",
        name="Owned",
        project_id=None,
        created_by=users["viewer"].id,
    )
    unowned_gate = QualityGate(
        id="legacy-gate",
        name="Legacy gate",
        project_id=None,
        rules="[]",
    )
    db_session.add_all([owned, unowned_gate])
    db_session.commit()
    current = {"user": users["viewer"]}

    with _client(db_session, current) as client:
        assert client.get(f"/api/v1/workflows/{owned.id}").status_code == 200
        assert (
            client.get(f"/api/v1/quality-gates/{unowned_gate.id}/results").status_code
            == 403
        )

        current["user"] = users["outsider"]
        assert client.get(f"/api/v1/workflows/{owned.id}").status_code == 403

        current["user"] = users["superuser"]
        assert (
            client.get(f"/api/v1/quality-gates/{unowned_gate.id}/results").status_code
            == 200
        )


def test_recording_session_is_limited_to_its_creator(db_session, monkeypatch):
    users, _, _ = _seed_projects_and_roles(db_session)
    session_id = "recording-owner-session"
    current = {"user": users["viewer"]}
    monkeypatch.setitem(
        ui_test_cases_api._recording_owners,
        session_id,
        users["viewer"].id,
    )
    monkeypatch.setattr(
        "app.api.v1.ui_test_cases.get_recording_events",
        lambda session_id: {"session_id": session_id, "events": []},
    )

    with _client(db_session, current) as client:
        path = f"/api/v1/ui-test-cases/recording/{session_id}/events"
        assert client.get(path).status_code == 200

        current["user"] = users["outsider"]
        assert client.get(path).status_code == 403
        assert (
            client.get(
                "/api/v1/ui-test-cases/recording/missing-session/events"
            ).status_code
            == 404
        )
