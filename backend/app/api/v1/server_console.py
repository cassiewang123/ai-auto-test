"""服务器连接工具：通过 SSH 在远程服务器执行受限 curl 命令.

安全边界：
    1. 只允许 `curl` / `curl.exe` 开头的命令，拒绝管道、重定向、命令串联和命令替换；
    2. 只允许 GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS 等 HTTP 方法；
    3. 对命令中出现的 http(s) URL 做 SSRF 校验（复用 URLPolicy，默认拒绝私有地址）；
    4. 连接凭据只用于当前请求，不落库；单次执行有超时和输出大小上限。

工具集页面需要远程调试内网/公网接口时使用，属于受 JWT 保护的管理能力。
"""
from __future__ import annotations

import re
import shlex
import time
from typing import Any

import paramiko
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.exceptions import ValidationError
from app.services.security.url_policy import URLPolicy

router = APIRouter()

_ALLOWED_BINARIES = {"curl", "curl.exe"}
_ALLOWED_METHODS = {
    "GET",
    "HEAD",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
}
# 禁止管道、重定向、命令串联/替换、后台执行、子 shell
_FORBIDDEN_SHELL = re.compile(r"[|;&>`$]|\$\(|&&|\|\||\$\{")
_URL_PATTERN = re.compile(r"https?://[^\s'\"]+", re.IGNORECASE)


class SSHConnection(BaseModel):
    host: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    port: int = Field(22, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(..., min_length=1, max_length=512)
    # 是否允许 curl 访问私有/内网地址；默认沿用系统 URL_ALLOW_PRIVATE 配置
    allow_private: bool | None = None


class SSHTestRequest(SSHConnection):
    timeout: int = Field(20, ge=5, le=120)


class SSHRunRequest(SSHConnection):
    command: str = Field(..., min_length=1, max_length=20_000)
    timeout: int = Field(60, ge=5, le=300)


class SSHTestResponse(BaseModel):
    ok: bool
    message: str
    server_banner: str | None = None


class SSHRunResponse(BaseModel):
    exit_code: int | None
    stdout: str
    stderr: str
    duration: float
    truncated: bool
    command: str


def _build_url_policy(allow_private: bool | None = None) -> URLPolicy:
    settings = get_settings()
    return URLPolicy(
        allow_private=(
            settings.URL_ALLOW_PRIVATE if allow_private is None else allow_private
        ),
        allowed_domains=[
            d.strip()
            for d in settings.URL_ALLOWED_DOMAINS.split(",")
            if d.strip()
        ],
        blocked_domains=[
            d.strip()
            for d in settings.URL_BLOCKED_DOMAINS.split(",")
            if d.strip()
        ],
    )


def validate_curl_command(
    command: str, allow_private: bool | None = None
) -> str:
    """校验远程命令，只允许单条 curl 且不包含 shell 注入语法."""
    normalized = command.strip()
    if not normalized:
        raise ValidationError("命令不能为空")
    if "\n" in normalized or "\r" in normalized:
        raise ValidationError("命令不能包含多行")
    if _FORBIDDEN_SHELL.search(normalized):
        raise ValidationError("不允许管道、重定向、命令串联或变量展开")
    try:
        tokens = shlex.split(normalized, posix=True)
    except ValueError as exc:
        raise ValidationError(f"命令无法解析: {exc}") from exc
    if not tokens:
        raise ValidationError("命令不能为空")
    binary = tokens[0].rsplit("/", 1)[-1].lower()
    if binary not in _ALLOWED_BINARIES:
        raise ValidationError("只允许执行 curl 命令")

    policy = _build_url_policy(allow_private)
    urls = _URL_PATTERN.findall(normalized)
    if not urls:
        raise ValidationError("命令中必须包含 http(s) URL")
    for url in urls:
        allowed, reason = policy.validate(url.rstrip(",;"))
        if not allowed:
            raise ValidationError(f"目标地址不被允许: {reason}")
    return normalized


def _apply_method_guard(command: str) -> None:
    """解析 curl 的 -X/--request 参数，校验 HTTP 方法."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValidationError(f"命令无法解析: {exc}") from exc
    method = "GET"
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in ("-X", "--request") and index + 1 < len(tokens):
            method = tokens[index + 1].upper()
            index += 2
            continue
        if token.startswith("--request="):
            method = token.split("=", 1)[1].upper()
        elif token.startswith("-X") and len(token) > 2:
            method = token[2:].upper()
        index += 1
    if method not in _ALLOWED_METHODS:
        raise ValidationError(f"不允许的 HTTP 方法: {method}")


def _read_limited(channel: paramiko.ChannelFile, limit: int) -> tuple[bytes, bool]:
    data = channel.read()
    if data is None:
        return b"", False
    truncated = len(data) > limit
    return data[:limit], truncated


class _SSHClient:
    """封装连接与执行，便于测试时注入替身."""

    def __init__(self, request: SSHConnection, timeout: int):
        self.request = request
        self.timeout = timeout
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def connect(self) -> None:
        self.client.connect(
            hostname=self.request.host,
            port=self.request.port,
            username=self.request.username,
            password=self.request.password,
            timeout=self.timeout,
            banner_timeout=self.timeout,
            auth_timeout=self.timeout,
            look_for_keys=False,
            allow_agent=False,
        )

    def get_banner(self) -> str | None:
        transport = self.client.get_transport()
        return transport.get_banner() if transport else None

    def run(self, command: str, max_output: int) -> tuple[int | None, str, str, bool]:
        stdin, stdout, stderr = self.client.exec_command(command, timeout=self.timeout)
        stdout_data, stdout_truncated = _read_limited(stdout, max_output)
        stderr_data, stderr_truncated = _read_limited(stderr, max_output - len(stdout_data))
        exit_code = stdout.channel.recv_exit_status()
        return (
            exit_code,
            stdout_data.decode("utf-8", "replace"),
            stderr_data.decode("utf-8", "replace"),
            stdout_truncated or stderr_truncated,
        )

    def close(self) -> None:
        self.client.close()


@router.post("/ssh/test", response_model=dict[str, Any])
def test_ssh_connection(req: SSHTestRequest) -> dict[str, Any]:
    """测试 SSH 连接是否可用（不会执行任何命令）."""
    client = _SSHClient(req, req.timeout)
    try:
        client.connect()
        banner = client.get_banner()
        return {
            "code": 0,
            "message": "连接成功",
            "data": {"ok": True, "message": "连接成功", "server_banner": banner},
        }
    except paramiko.AuthenticationException as exc:
        raise ValidationError("SSH 认证失败，请检查用户名和密码") from exc
    except Exception as exc:  # noqa: BLE001 - 统一转换为可读错误
        raise ValidationError(f"SSH 连接失败: {exc}") from exc
    finally:
        client.close()


@router.post("/ssh/execute", response_model=dict[str, Any])
def execute_curl(req: SSHRunRequest) -> dict[str, Any]:
    """通过 SSH 执行一条 curl 命令并返回标准输出/错误输出."""
    command = validate_curl_command(req.command, req.allow_private)
    _apply_method_guard(command)

    started = time.perf_counter()
    client = _SSHClient(req, req.timeout)
    try:
        client.connect()
        exit_code, stdout, stderr, truncated = client.run(
            command, min(get_settings().URL_MAX_RESPONSE_SIZE, 2 * 1024 * 1024)
        )
        return {
            "code": 0,
            "message": "执行完成",
            "data": {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "duration": round(time.perf_counter() - started, 3),
                "truncated": truncated,
                "command": command,
            },
        }
    except paramiko.AuthenticationException as exc:
        raise ValidationError("SSH 认证失败，请检查用户名和密码") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"SSH 执行失败: {exc}") from exc
    finally:
        client.close()
