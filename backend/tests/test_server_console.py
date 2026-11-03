"""服务器连接工具：curl 命令校验与执行接口测试."""
from __future__ import annotations

import pytest

from app.api.v1.server_console import _apply_method_guard, validate_curl_command
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


def test_accepts_post_curl():
    command = (
        "curl -sS -X POST 'https://api.example.com/v1/orders' "
        "-H 'Content-Type: application/json' -d '{\"id\": 1}'"
    )
    assert validate_curl_command(command) == command
    _apply_method_guard(command)


def test_accepts_get_curl_without_explicit_method():
    command = "curl -sS 'https://api.example.com/v1/ping'"
    validate_curl_command(command)
    _apply_method_guard(command)


@pytest.mark.parametrize(
    "command",
    [
        "wget https://api.example.com/v1/ping",
        "bash -c 'curl https://api.example.com'",
        "curl https://api.example.com; rm -rf /",
        "curl https://api.example.com | sh",
        "curl https://api.example.com > /tmp/out",
        "curl https://api.example.com && echo done",
        "curl https://api.example.com $(whoami)",
        "curl https://api.example.com\nrm -rf /",
    ],
)
def test_rejects_non_curl_or_injection(command):
    with pytest.raises(ValidationError):
        validate_curl_command(command)


def test_rejects_curl_without_url():
    with pytest.raises(ValidationError):
        validate_curl_command("curl -sS -X POST -d '{}'")


def test_rejects_unknown_http_method():
    command = "curl -X TRACE 'https://api.example.com/v1/ping'"
    validate_curl_command(command)
    with pytest.raises(ValidationError):
        _apply_method_guard(command)


def test_rejects_unsupported_protocol():
    with pytest.raises(ValidationError):
        validate_curl_command("curl -sS 'file:///etc/passwd'")


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


def _payload(command: str) -> dict:
    return {
        "host": "snowflow.cloud",
        "port": 22,
        "username": "yhztd",
        "password": "secret",
        "command": command,
    }


def test_execute_endpoint_returns_stdout(client, fake_ssh):
    response = client.post(
        "/api/v1/tools/ssh/execute",
        json=_payload("curl -sS -X POST 'https://api.example.com/v1/orders' -d '{\"id\": 1}'"),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["exit_code"] == 0
    assert data["stdout"] == '{"ok": true}'
    assert fake_ssh.calls and "api.example.com" in fake_ssh.calls[0]


def test_execute_endpoint_rejects_injection(client, fake_ssh):
    response = client.post(
        "/api/v1/tools/ssh/execute",
        json=_payload("curl https://api.example.com; whoami"),
    )
    assert response.status_code in (400, 422)
    assert not fake_ssh.calls


def test_connection_test_endpoint(client, fake_ssh):
    response = client.post(
        "/api/v1/tools/ssh/test",
        json={
            "host": "snowflow.cloud",
            "port": 22,
            "username": "yhztd",
            "password": "secret",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is True
    assert data["server_banner"] == "SSH-2.0-Fake"
