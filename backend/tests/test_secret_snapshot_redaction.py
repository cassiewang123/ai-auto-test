"""Credential redaction across execution responses, snapshots, and history."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.api.v1.test_plans import _serialize_chain_result
from app.models.call_history import CallHistory
from app.models.environment import Environment
from app.models.execution_job import JobEvent
from app.models.test_case import TestCase as ORMTestCase
from app.models.test_result import TestResult as ORMTestResult
from app.schemas.execution import ExecutionResult, RequestDefinition, ResponseData
from app.services.data_driven_service import execute_data_driven
from app.services.execution.job_service import JobService
from app.services.security.data_redaction import (
    REDACTED_VALUE,
    redact_sensitive_data,
)
from app.services.security.secret_crypto import encrypt_secret


def _execution_result(request_def: RequestDefinition) -> ExecutionResult:
    return ExecutionResult(
        test_case_id="redaction-case",
        status="passed",
        duration=0.01,
        request=request_def,
        response=ResponseData(
            status_code=200,
            headers={
                "Set-Cookie": "server=server-cookie; Path=/; HttpOnly",
                "X-Trace": "trace-1",
            },
            body={"access_token": "response-token", "value": "kept"},
            elapsed=0.01,
            text="Authorization: Bearer response-token",
        ),
        assertion_results=[],
        extracted_variables=[],
    )


def _execute_side_effect(**kwargs):
    return _execution_result(kwargs["request_def"])


def test_recursive_redaction_is_fixed_non_mutating_and_context_aware() -> None:
    source = {
        "headers": {
            "Authorization": "Bearer auth-secret",
            "Cookie": "session=cookie-secret",
            "X-Trace": "trace-1",
        },
        "response_headers": {
            "Set-Cookie": "server=response-cookie",
            "Content-Type": "application/json",
        },
        "cookies": [
            {
                "name": "session",
                "value": "cookie-value",
                "path": "/",
            }
        ],
        "nested": {
            "password": "db-password",
            "client_secret": "client-secret",
            "access_token": "access-token",
            "value": "ordinary-value",
            "token_usage_total": 42,
            "has_secret": True,
        },
        "extracted_variables": [
            {"name": "access_token", "value": "extracted-secret", "source": "body"},
            {"name": "user_id", "value": 42, "source": "body"},
        ],
        "message": "Authorization: Bearer inline-secret",
        "basic_message": "Authorization: Basic basic-secret",
    }

    redacted = redact_sensitive_data(source)

    assert redacted["headers"]["Authorization"] == REDACTED_VALUE
    assert redacted["headers"]["Cookie"] == REDACTED_VALUE
    assert redacted["headers"]["X-Trace"] == "trace-1"
    assert redacted["response_headers"]["Set-Cookie"] == REDACTED_VALUE
    assert redacted["cookies"][0]["value"] == REDACTED_VALUE
    assert redacted["nested"]["password"] == REDACTED_VALUE
    assert redacted["nested"]["client_secret"] == REDACTED_VALUE
    assert redacted["nested"]["access_token"] == REDACTED_VALUE
    assert redacted["nested"]["value"] == "ordinary-value"
    assert redacted["nested"]["token_usage_total"] == 42
    assert redacted["nested"]["has_secret"] is True
    assert redacted["extracted_variables"][0]["value"] == REDACTED_VALUE
    assert redacted["extracted_variables"][1]["value"] == 42
    assert redacted["message"] == f"Authorization: {REDACTED_VALUE}"
    assert redacted["basic_message"] == f"Authorization: {REDACTED_VALUE}"
    assert source["headers"]["Authorization"] == "Bearer auth-secret"
    assert source["cookies"][0]["value"] == "cookie-value"


def test_chain_result_serialization_redacts_transport_credentials() -> None:
    request = RequestDefinition(
        method="GET",
        url="https://example.com/chain",
        headers={
            "Authorization": "Bearer chain-auth-secret",
            "Cookie": "session=chain-cookie-secret",
        },
    )

    serialized = _serialize_chain_result(_execution_result(request))

    assert serialized["request"]["headers"]["Authorization"] == REDACTED_VALUE
    assert serialized["request"]["headers"]["Cookie"] == REDACTED_VALUE
    assert serialized["response"]["headers"]["Set-Cookie"] == REDACTED_VALUE
    assert serialized["response"]["body"]["access_token"] == REDACTED_VALUE


def test_sync_execution_response_and_history_are_redacted(
    client,
    db_session,
) -> None:
    with patch(
        "app.api.v1.execution._executor.execute",
        side_effect=_execute_side_effect,
    ):
        response = client.post(
            "/api/v1/execution/run",
            json={
                "method": "GET",
                "url": "https://example.com/secure",
                "headers": {
                    "Authorization": "Bearer sync-auth-secret",
                    "X-Trace": "trace-1",
                },
                "cookies": [{"name": "session", "value": "sync-cookie-secret"}],
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["request"]["headers"]["Authorization"] == REDACTED_VALUE
    assert data["request"]["headers"]["Cookie"] == REDACTED_VALUE
    assert data["response"]["headers"]["Set-Cookie"] == REDACTED_VALUE
    assert data["response"]["headers"]["X-Trace"] == "trace-1"
    assert data["response"]["body"]["access_token"] == REDACTED_VALUE
    assert data["response"]["body"]["value"] == "kept"
    assert data["session_cookies"][0]["value"] == REDACTED_VALUE
    assert "sync-auth-secret" not in response.text
    assert "sync-cookie-secret" not in response.text

    history = db_session.query(CallHistory).one()
    assert history.headers["Authorization"] == REDACTED_VALUE
    assert history.response_headers["Set-Cookie"] == REDACTED_VALUE
    assert history.response_body["access_token"] == REDACTED_VALUE
    assert history.response_body["value"] == "kept"


def test_multipart_execution_history_never_persists_cookie_header(
    client,
    db_session,
) -> None:
    with patch(
        "app.api.v1.execution._executor.execute",
        side_effect=_execute_side_effect,
    ):
        response = client.post(
            "/api/v1/execution/run-multipart",
            data={
                "method": "POST",
                "url": "https://example.com/upload",
                "headers": json.dumps({"Authorization": "Bearer multipart-auth-secret"}),
                "params": "{}",
                "body": "{}",
                "assertions": "[]",
                "variables": "{}",
                "pre_requests": "[]",
                "cookies": json.dumps([{"name": "session", "value": "multipart-cookie-secret"}]),
            },
        )

    assert response.status_code == 200, response.text
    assert "multipart-auth-secret" not in response.text
    assert "multipart-cookie-secret" not in response.text
    history = db_session.query(CallHistory).one()
    assert history.headers["Authorization"] == REDACTED_VALUE
    assert history.headers["Cookie"] == REDACTED_VALUE


def test_saved_case_snapshot_and_report_mask_decrypted_environment_cookie(
    client,
    db_session,
) -> None:
    encrypted_cookie = encrypt_secret("saved-environment-cookie")
    environment = Environment(
        name="snapshot-env",
        base_url="https://example.com",
        variables={},
        cookies=[{"name": "session", "value": encrypted_cookie}],
    )
    db_session.add(environment)
    db_session.flush()
    case = ORMTestCase(
        title="snapshot-case",
        method="GET",
        url="/secure",
        headers={"Authorization": "Bearer saved-auth-secret"},
        params={},
        markers=[],
        extract_rules=[],
        environment_id=environment.id,
    )
    db_session.add(case)
    db_session.commit()

    captured_request: dict[str, RequestDefinition] = {}

    def execute_saved(**kwargs):
        captured_request["value"] = kwargs["request_def"]
        return _execution_result(kwargs["request_def"])

    with patch(
        "app.api.v1.execution._executor.execute",
        side_effect=execute_saved,
    ):
        response = client.post(f"/api/v1/execution/run/{case.id}")

    assert response.status_code == 200, response.text
    outbound_headers = captured_request["value"].headers
    assert outbound_headers["Cookie"] == "session=saved-environment-cookie"
    assert outbound_headers["Authorization"] == "Bearer saved-auth-secret"
    assert "saved-environment-cookie" not in response.text
    assert "saved-auth-secret" not in response.text

    stored = db_session.query(ORMTestResult).one()
    assert stored.request_snapshot["headers"]["Cookie"] == REDACTED_VALUE
    assert stored.request_snapshot["headers"]["Authorization"] == REDACTED_VALUE
    assert stored.response_snapshot["headers"]["Set-Cookie"] == REDACTED_VALUE

    report = client.get(f"/api/v1/reports/runs/{stored.run_id}/results")
    assert report.status_code == 200, report.text
    report_item = report.json()["data"][0]
    assert report_item["request_snapshot"]["headers"]["Cookie"] == REDACTED_VALUE
    assert report_item["request_snapshot"]["headers"]["Authorization"] == REDACTED_VALUE
    assert "saved-environment-cookie" not in report.text
    assert "saved-auth-secret" not in report.text


def test_history_and_reports_redact_legacy_plaintext_rows(
    client,
    db_session,
) -> None:
    history = CallHistory(
        method="GET",
        url="https://example.com",
        status="passed",
        headers={
            "Authorization": "Bearer legacy-auth",
            "Cookie": "session=legacy-cookie",
        },
        response_headers={"Set-Cookie": "server=legacy-response-cookie"},
        response_body={"refresh_token": "legacy-token", "value": "kept"},
        response_text="Authorization: Bearer legacy-text-token",
    )
    result = ORMTestResult(
        run_id="legacy-run",
        test_case_id="legacy-case",
        status="passed",
        request_snapshot={
            "headers": {
                "Authorization": "Bearer legacy-report-auth",
                "Cookie": "session=legacy-report-cookie",
            }
        },
        response_snapshot={"headers": {"Set-Cookie": "server=legacy-report-response"}},
    )
    db_session.add_all([history, result])
    db_session.commit()

    history_response = client.get(f"/api/v1/history/{history.id}")
    assert history_response.status_code == 200, history_response.text
    history_data = history_response.json()["data"]
    assert history_data["headers"]["Authorization"] == REDACTED_VALUE
    assert history_data["headers"]["Cookie"] == REDACTED_VALUE
    assert history_data["response_headers"]["Set-Cookie"] == REDACTED_VALUE
    assert history_data["response_body"]["refresh_token"] == REDACTED_VALUE
    assert history_data["response_body"]["value"] == "kept"
    assert "legacy-auth" not in history_response.text
    assert client.get("/api/v1/history/stats").status_code == 200

    report_response = client.get("/api/v1/reports/runs/legacy-run/results")
    assert report_response.status_code == 200, report_response.text
    report_data = report_response.json()["data"][0]
    assert report_data["request_snapshot"]["headers"]["Authorization"] == REDACTED_VALUE
    assert report_data["request_snapshot"]["headers"]["Cookie"] == REDACTED_VALUE
    assert report_data["response_snapshot"]["headers"]["Set-Cookie"] == REDACTED_VALUE
    assert "legacy-report-auth" not in report_response.text
    assert "legacy-report-cookie" not in report_response.text


def test_async_job_uses_plain_environment_cookie_but_persists_masks(
    db_session,
) -> None:
    encrypted_cookie = encrypt_secret("job-environment-cookie")
    environment = Environment(
        name="job-env",
        base_url="https://example.com",
        variables={"tenant": "tenant-1"},
        cookies=[{"name": "session", "value": encrypted_cookie}],
    )
    db_session.add(environment)
    db_session.flush()
    case = ORMTestCase(
        title="job-case",
        method="GET",
        url="/secure",
        headers={"Authorization": "Bearer job-auth-secret"},
        params={},
        markers=[],
        extract_rules=[],
        environment_id=environment.id,
    )
    db_session.add(case)
    db_session.commit()

    service = JobService(db_session)
    job = service.create_job(
        job_type="api_case",
        resource_id=case.id,
        config={
            "headers": {"Authorization": "Bearer config-auth-secret"},
            "cookies": [{"name": "config", "value": "config-cookie-secret"}],
        },
    )
    snapshot = json.loads(job.request_snapshot)
    assert snapshot["headers"]["Authorization"] == REDACTED_VALUE
    assert snapshot["cookies"][0]["value"] == REDACTED_VALUE
    assert job.config["headers"]["Authorization"] == REDACTED_VALUE
    assert job.config["cookies"][0]["value"] == REDACTED_VALUE

    mock_result = SimpleNamespace(
        status="passed",
        duration=0.01,
        response=SimpleNamespace(status_code=200),
        error_message=None,
    )
    with patch("test_engine.executor.TestCaseExecutor") as executor_class:
        executor_class.return_value.execute.return_value = mock_result
        completed = service.execute_job(job.id, worker_id="audit-worker")

    execute_call = executor_class.return_value.execute.call_args
    request_def = execute_call.kwargs["request_def"]
    assert request_def.headers["Cookie"] == "session=job-environment-cookie"
    assert request_def.headers["Authorization"] == "Bearer job-auth-secret"
    assert execute_call.kwargs["variables"] == {"tenant": "tenant-1"}
    assert completed.status == "succeeded"

    event_payloads = [event.payload for event in db_session.query(JobEvent).filter(JobEvent.job_id == job.id)]
    persisted = "\n".join(payload for payload in event_payloads if payload)
    assert "job-environment-cookie" not in persisted
    assert "job-auth-secret" not in persisted
    assert "config-cookie-secret" not in persisted


def test_data_driven_uses_decrypted_cookie_without_returning_it() -> None:
    encrypted_cookie = encrypt_secret("data-environment-cookie")
    environment = SimpleNamespace(
        base_url="https://example.com",
        variables={"tenant": "tenant-1"},
        cookies=[{"name": "session", "value": encrypted_cookie}],
    )
    case = SimpleNamespace(
        method="GET",
        url="/users/{{user}}",
        headers={"X-Tenant": "{{tenant}}"},
        params={},
        body=None,
        graphql_query=None,
        extract_rules=[],
        assertions=[],
    )
    mock_result = MagicMock()
    mock_result.status = "passed"
    mock_result.duration = 0.01
    mock_result.response.status_code = 200
    mock_result.assertion_results = []
    mock_result.error_message = None

    with patch("test_engine.executor.TestCaseExecutor") as executor_class:
        executor_class.return_value.execute.return_value = mock_result
        results = execute_data_driven(
            case,
            [
                {
                    "user": "alice",
                    "Authorization": "Bearer row-auth-secret",
                    "Cookie": "row-cookie-secret",
                }
            ],
            environment=environment,
        )

    request_def = executor_class.return_value.execute.call_args.kwargs["request_def"]
    assert request_def.headers["Cookie"] == "session=data-environment-cookie"
    assert request_def.headers["X-Tenant"] == "tenant-1"
    assert results[0]["input_data"] == {
        "user": "alice",
        "Authorization": REDACTED_VALUE,
        "Cookie": REDACTED_VALUE,
    }
    assert "data-environment-cookie" not in json.dumps(results)
    assert "row-auth-secret" not in json.dumps(results)
    assert "row-cookie-secret" not in json.dumps(results)
