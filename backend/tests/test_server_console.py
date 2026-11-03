"""服务器连接工具：结构化 HTTP 请求生成 curl 与执行接口测试."""
from __future__ import annotations

import pytest

from app.api.v1.server_console import SSHCurlRequest, build_curl_command
from app.core.exceptions import ValidationError


@pytest.fixture(autouse=True)
def allow_public_host(monkeypatch):
    # 单元测试不依赖真实 DNS，直接放行校验
    class _AllowAllPolicy:
        def __init__(self, allow_private: bool | None = None):
            self.allow_private = allow_private

        def validate(self, url: str) -> tuple[bool, str]:
            return True, "OK"

    monkeypatch.setattr(
        "app.api.v1.server_console._build_url_policy",
        _AllowAllPolicy,
    )


def _request(**overrides) -> SSHCurlRequest:
    payload = {
        "host": "snowflow.cloud",
        "port": 22,
        "username": "yhztd",
        "password": "secret",
    }
    payload.update(overrides)
    return SSHCurlRequest(**payload)


def test_builds_post_request_with_headers_and_body():
    req = _request(
        method="post",
        url="https://api.example.com/v1/orders",
        headers={"Content-Type": "application/json", "X-Token": "abc"},
        body='{"id": 1}',
    )
    command = build_curl_command(req)
    assert command.startswith("curl -sS -X POST https://api.example.com/v1/orders")
    assert "-H 'Content-Type: application/json'" in command
    assert "-H 'X-Token: abc'" in command
    assert "--data-raw" in command
    assert "'{\"id\": 1}'" in command


def test_builds_get_request_with_query_params():
    req = _request(
        method="GET",
        url="https://api.example.com/v1/list?page=1",
        params={"size": "20", "q": "a b"},
    )
    command = build_curl_command(req)
    assert "-X GET" in command
    assert "page=1&size=20&q=a+b" in command
    assert "--data-raw" not in command


def test_quotes_shell_metacharacters():
    req = _request(
        method="POST",
        url="https://api.example.com/v1/x",
        headers={"X-Note": "a;rm -rf /"},
        body='{"name":"$(id)"}',
    )
    command = build_curl_command(req)
    # 危险内容必须整体被单引号包裹，不能裸露成 shell 语法
    assert "'X-Note: a;rm -rf /'" in command
    assert "'{\"name\":\"$(id)\"}'" in command


def test_rejects_non_http_url():
    with pytest.raises(ValidationError):
        build_curl_command(_request(url="file:///etc/passwd"))


def test_rejects_invalid_method():
    with pytest.raises(ValueError):
        _request(method="TRACE", url="https://api.example.com")


def test_rejects_header_newline_injection():
    with pytest.raises(ValidationError):
        build_curl_command(
            _request(url="https://api.example.com", headers={"X-Test": "a\r\nB: c"})
        )


def test_rejects_invalid_header_name():
    with pytest.raises(ValidationError):
        build_curl_command(
            _request(url="https://api.example.com", headers={"Bad Name": "x"})
        )


@pytest.fixture
def fake_ssh(monkeypatch):
    class FakeClient:
        calls: list[str] = []

        def __init__(self, request, timeout):
            self.request = request
            self.timeout = timeout

        def connect(self):
            pass

        def get_banner(self):
            return "SSH-2.0-Fake"

        def run(self, command, max_output):
            FakeClient.calls.append(command)
            return 0, '{"ok": true}', "", False

        def close(self):
            pass

    monkeypatch.setattr("app.api.v1.server_console._SSHClient", FakeClient)
    return FakeClient


def _connection_payload(**overrides) -> dict:
    payload = {
        "host": "snowflow.cloud",
        "port": 22,
        "username": "yhztd",
        "password": "secret",
    }
    payload.update(overrides)
    return payload


def test_request_endpoint_executes_generated_curl(client, fake_ssh):
    response = client.post(
        "/api/v1/tools/ssh/request",
        json=_connection_payload(
            method="POST",
            url="https://api.example.com/v1/orders",
            headers={"Content-Type": "application/json"},
            body='{"id": 1}',
        ),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["exit_code"] == 0
    assert data["stdout"] == '{"ok": true}'
    assert data["command"].startswith("curl -sS -X POST")
    assert fake_ssh.calls and "api.example.com/v1/orders" in fake_ssh.calls[0]


def test_request_endpoint_rejects_bad_url(client, fake_ssh):
    response = client.post(
        "/api/v1/tools/ssh/request",
        json=_connection_payload(url="file:///etc/passwd"),
    )
    assert response.status_code in (400, 422)
    assert not fake_ssh.calls


def test_connection_test_endpoint(client, fake_ssh):
    response = client.post("/api/v1/tools/ssh/test", json=_connection_payload())
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is True
    assert data["server_banner"] == "SSH-2.0-Fake"


def _saved_payload(**overrides) -> dict:
    payload = {
        "name": "查询订单",
        "method": "POST",
        "url": "https://api.example.com/v1/orders",
        "params": {"page": "1"},
        "headers": {"Content-Type": "application/json"},
        "body": '{"id": 1}',
    }
    payload.update(overrides)
    return payload


def test_saved_request_crud(client):
    created = client.post("/api/v1/tools/saved-requests", json=_saved_payload())
    assert created.status_code == 200
    item = created.json()["data"]
    assert item["name"] == "查询订单"
    assert item["params"] == {"page": "1"}
    request_id = item["id"]

    listed = client.get("/api/v1/tools/saved-requests")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["data"]] == [request_id]

    updated = client.put(
        f"/api/v1/tools/saved-requests/{request_id}",
        json=_saved_payload(name="查询订单-新", method="GET", body=None),
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "查询订单-新"
    assert updated.json()["data"]["method"] == "GET"

    deleted = client.delete(f"/api/v1/tools/saved-requests/{request_id}")
    assert deleted.status_code == 200
    assert client.get("/api/v1/tools/saved-requests").json()["data"] == []


def test_saved_request_rejects_bad_method_and_url(client):
    bad_method = client.post(
        "/api/v1/tools/saved-requests", json=_saved_payload(method="TRACE")
    )
    assert bad_method.status_code == 422

    bad_url = client.post(
        "/api/v1/tools/saved-requests", json=_saved_payload(url="file:///etc/passwd")
    )
    assert bad_url.status_code == 422


def test_saved_request_rejects_header_injection(client):
    response = client.post(
        "/api/v1/tools/saved-requests",
        json=_saved_payload(headers={"X-Test": "a\r\nB: c"}),
    )
    assert response.status_code in (400, 422)
