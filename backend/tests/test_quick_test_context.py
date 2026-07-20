"""Quick-test project and environment context integration."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.models.call_history import CallHistory
from app.models.environment import Environment
from app.models.global_variable import GlobalVariable
from app.models.project import Project
from app.schemas.execution import ExecutionResult, RequestDefinition, ResponseData
from app.services.security.data_redaction import REDACTED_VALUE
from app.services.security.secret_crypto import encrypt_secret


def _execution_result(request_def: RequestDefinition) -> ExecutionResult:
    return ExecutionResult(
        test_case_id="quick-test-context",
        status="passed",
        duration=0.01,
        request=request_def,
        response=ResponseData(
            status_code=200,
            headers={},
            body={"ok": True},
            elapsed=0.01,
            text='{"ok": true}',
        ),
    )


def _workspace_context(db_session):
    project = Project(name="Quick test project")
    db_session.add(project)
    db_session.flush()
    db_session.add(
        GlobalVariable(
            name="workspace_value",
            value="workspace",
            var_type="string",
            scope="workspace",
            project_id=project.id,
        )
    )
    environment = Environment(
        name="Quick test environment",
        base_url="https://environment.example/api",
        variables={"environment_value": "environment", "shared": "environment"},
        cookies=[
            {
                "name": "session",
                "value": encrypt_secret("environment-cookie"),
            }
        ],
    )
    db_session.add(environment)
    db_session.commit()
    return project, environment


def test_json_quick_test_loads_workspace_and_environment_context(
    client,
    db_session,
) -> None:
    project, environment = _workspace_context(db_session)
    captured: dict[str, object] = {}

    def execute(**kwargs):
        captured.update(kwargs)
        return _execution_result(kwargs["request_def"])

    with patch("app.api.v1.execution._executor.execute", side_effect=execute):
        response = client.post(
            "/api/v1/execution/run",
            json={
                "method": "GET",
                "url": "/users",
                "headers": {"X-Count": "123"},
                "variables": {"shared": "request", "request_value": "request"},
                "extract_rules": [
                    {
                        "name": "user_id",
                        "source": "json_path",
                        "expression": "$.id",
                    }
                ],
                "project_id": project.id,
                "environment_id": environment.id,
            },
        )

    assert response.status_code == 200, response.text
    request_def = captured["request_def"]
    assert isinstance(request_def, RequestDefinition)
    assert request_def.url == "https://environment.example/api/users"
    assert request_def.headers["X-Count"] == "123"
    assert request_def.headers["Cookie"] == "session=environment-cookie"
    assert request_def.extract_rules[0]["name"] == "user_id"
    assert captured["variables"] == {
        "workspace_value": "workspace",
        "environment_value": "environment",
        "shared": "request",
        "request_value": "request",
    }

    history = db_session.query(CallHistory).one()
    assert history.project_id == project.id
    assert history.url == "https://environment.example/api/users"
    assert history.headers["Cookie"] == REDACTED_VALUE


def test_multipart_quick_test_uses_same_context_contract(
    client,
    db_session,
) -> None:
    project, environment = _workspace_context(db_session)
    captured: dict[str, object] = {}

    def execute(**kwargs):
        captured.update(kwargs)
        return _execution_result(kwargs["request_def"])

    with patch("app.api.v1.execution._executor.execute", side_effect=execute):
        response = client.post(
            "/api/v1/execution/run-multipart",
            data={
                "method": "POST",
                "url": "/upload",
                "headers": json.dumps({"X-Mode": "multipart"}),
                "params": "{}",
                "body": "{}",
                "extract_rules": json.dumps(
                    [
                        {
                            "name": "upload_id",
                            "source": "header",
                            "expression": "X-Upload-Id",
                        }
                    ]
                ),
                "assertions": "[]",
                "variables": json.dumps({"shared": "multipart"}),
                "pre_requests": "[]",
                "cookies": "[]",
                "project_id": project.id,
                "environment_id": environment.id,
            },
        )

    assert response.status_code == 200, response.text
    request_def = captured["request_def"]
    assert isinstance(request_def, RequestDefinition)
    assert request_def.url == "https://environment.example/api/upload"
    assert request_def.headers["Cookie"] == "session=environment-cookie"
    assert request_def.extract_rules[0]["name"] == "upload_id"
    assert captured["variables"]["shared"] == "multipart"

    history = db_session.query(CallHistory).one()
    assert history.project_id == project.id
    assert history.url == "https://environment.example/api/upload"
