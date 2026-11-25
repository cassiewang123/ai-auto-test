"""服务器连接工具：通过 SSH 在远程服务器上请求 HTTP 接口.

页面只提供结构化输入（方法、URL、参数、请求头、请求体），由后端安全地拼成
curl 命令后执行，不接受任意 shell 命令。

安全边界：
    1. 只允许 GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS；
    2. URL 必须是 http(s)，并通过 URLPolicy 做 SSRF 校验；
    3. 所有参数经 shlex.quote 转义，请求头拒绝换行注入；
    4. 连接凭据只用于当前请求，不落库；单次执行有超时和输出大小上限。

工具集页面需要远程调试内网/公网接口时使用，属于受 JWT 保护的管理能力。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re
import shlex
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import paramiko
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.database import get_db
from app.models.server_saved_request import ServerSavedRequest
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.security.audit_service import log_audit
from app.services.security.url_policy import URLPolicy

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_METHODS = {
    "GET",
    "HEAD",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
}
_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+\-.^_`|~]+$")
_MAX_OUTPUT_BYTES = 2 * 1024 * 1024

# 进程内主机公钥白名单：key = "host:port"，value = 主机公钥指纹。
# 重启后端即清空，需重新显式信任一次；不落盘、不建 known_hosts 文件。
_TRUSTED_HOST_KEYS: dict[str, str] = {}


def _key_fingerprint(key: paramiko.PKey) -> str:
    """用标准库计算主机公钥的 SHA256 指纹（与 OpenSSH 展示口径一致）."""
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


class _ExplicitTrustPolicy(paramiko.MissingHostKeyPolicy):
    """默认拒绝自动信任主机密钥，仅接受显式指纹或进程内已信任指纹.

    未提供指纹且内存白名单未命中时，语义等价于 paramiko.RejectPolicy()。
    """

    def __init__(
        self,
        host: str,
        port: int,
        expected_fingerprint: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.expected_fingerprint = (expected_fingerprint or "").strip() or None

    def missing_host_key(
        self,
        client: paramiko.SSHClient,
        hostname: str,
        key: paramiko.PKey,
    ) -> None:
        """校验主机公钥指纹，拒绝未信任或已变更的主机密钥."""
        fingerprint = _key_fingerprint(key)
        host_key = f"{self.host}:{self.port}"
        trusted = _TRUSTED_HOST_KEYS.get(host_key)

        if trusted is not None and trusted != fingerprint:
            raise paramiko.SSHException(
                f"主机 {self.host}:{self.port} 的公钥指纹与已信任值不一致"
                f"（已信任 {trusted}，当前 {fingerprint}），已拒绝连接。"
                "请核对服务器是否变更或存在中间人攻击。"
            )
        if self.expected_fingerprint == fingerprint or trusted == fingerprint:
            _TRUSTED_HOST_KEYS[host_key] = fingerprint
            return
        raise paramiko.SSHException(
            f"目标主机 {self.host}:{self.port} 的公钥未被信任。"
            f"服务器返回指纹 {fingerprint}；请核对该指纹后填入「主机公钥指纹」"
            "再连接，避免中间人攻击。信任仅在本次后端进程内有效，重启后需重新确认。"
        )


def _require_console_enabled() -> None:
    """SSH 控制台后端权威闸：未启用时直接 403 并给出引导文案."""
    if not get_settings().SSH_CONSOLE_ENABLED:
        raise ForbiddenError(
            "服务器控制台未启用：请在 .env 设置 SSH_CONSOLE_ENABLED=true 并重启后端服务"
        )


def _write_ssh_audit(
    db: Session,
    current_user: User,
    action: str,
    req: SSHConnection,
    result: str,
    result_code: int | None,
) -> None:
    """为一次 SSH 调用写入 1 条最小审计（显式白名单，绝不含 password）.

    仅传入白名单字段，禁止 req.model_dump() 整体传入；审计失败不阻断主流程。
    """
    payload = {
        "host": req.host,
        "port": req.port,
        "method": getattr(req, "method", None),
        "url": getattr(req, "url", None),
        "ts": datetime.now(timezone.utc).isoformat(),
        "result_code": result_code,
    }
    try:
        log_audit(
            db,
            actor_id=current_user.id,
            actor_name=current_user.username,
            action=action,
            resource_type="server_console",
            resource_id=None,
            after=payload,
            result=result,
        )
    except Exception:  # noqa: BLE001 - 审计写入失败不影响主流程
        logger.exception("SSH 控制台审计写入失败")


class SSHConnection(BaseModel):
    host: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    port: int = Field(22, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(..., min_length=1, max_length=512)
    # 是否允许访问私有/内网地址；默认沿用系统 URL_ALLOW_PRIVATE 配置
    allow_private: bool | None = None
    # 显式信任的主机公钥指纹（SHA256:...）；不落盘，仅在本次后端进程内有效
    trust_host_fingerprint: str | None = None


class SSHTestRequest(SSHConnection):
    timeout: int = Field(20, ge=5, le=120)


class SSHCurlRequest(SSHConnection):
    method: str = Field("GET")
    url: str = Field(..., min_length=1, max_length=4096)
    params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(None, max_length=1_000_000)
    timeout: int = Field(60, ge=5, le=300)

    @field_validator("method")
    @classmethod
    def _validate_method(cls, value: str) -> str:
        method = value.strip().upper()
        if method not in ALLOWED_METHODS:
            raise ValueError(f"不允许的 HTTP 方法: {value}")
        return method


class ServerSavedRequestInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    method: str = Field("GET")
    url: str = Field(..., min_length=1, max_length=4096)
    params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(None, max_length=1_000_000)

    @field_validator("method")
    @classmethod
    def _validate_method(cls, value: str) -> str:
        method = value.strip().upper()
        if method not in ALLOWED_METHODS:
            raise ValueError(f"不允许的 HTTP 方法: {value}")
        return method

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        url = value.strip()
        if urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("接口地址必须以 http:// 或 https:// 开头")
        return url


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


def _append_query(url: str, params: dict[str, str]) -> str:
    if not params:
        return url
    parts = urlsplit(url)
    extra = urlencode(list(params.items()))
    query = f"{parts.query}&{extra}" if parts.query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _validate_headers(headers: dict[str, str]) -> None:
    for name, value in headers.items():
        if not name or not _HEADER_NAME.fullmatch(name):
            raise ValidationError(f"非法的请求头名称: {name!r}")
        if "\r" in value or "\n" in value:
            raise ValidationError(f"请求头 {name} 的值不能包含换行")


def build_curl_command(req: SSHCurlRequest) -> str:
    """把结构化请求拼成一条安全的 curl 命令（所有片段均做 shell 转义）."""
    url = req.url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValidationError("接口地址必须以 http:// 或 https:// 开头")
    if not parts.hostname:
        raise ValidationError("接口地址无效")

    allowed, reason = _build_url_policy(req.allow_private).validate(url)
    if not allowed:
        raise ValidationError(f"目标地址不被允许: {reason}")

    _validate_headers(req.headers)

    target = _append_query(url, req.params)
    args = ["curl", "-sS", "-X", req.method, shlex.quote(target)]
    for name, value in req.headers.items():
        args.extend(["-H", shlex.quote(f"{name}: {value}")])
    if req.body:
        args.extend(["--data-raw", shlex.quote(req.body)])
    return " ".join(args)


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
        # 默认拒绝自动信任主机密钥：仅接受显式指纹或进程内已信任指纹。
        self.client.set_missing_host_key_policy(
            _ExplicitTrustPolicy(
                host=request.host,
                port=request.port,
                expected_fingerprint=request.trust_host_fingerprint,
            )
        )

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
        _stdin, stdout, stderr = self.client.exec_command(command, timeout=self.timeout)
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
def test_ssh_connection(
    req: SSHTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """测试 SSH 连接是否可用（不会执行任何命令）."""
    audit_result = "failed"
    result_code: int | None = None
    client: _SSHClient | None = None
    try:
        # 后端权威闸：首个执行语句，未启用时直接 403（仍写 1 条失败审计）。
        _require_console_enabled()
        client = _SSHClient(req, req.timeout)
        client.connect()
        banner = client.get_banner()
        audit_result = "success"
        result_code = 0
        return {
            "code": 0,
            "message": "连接成功",
            "data": {"ok": True, "message": "连接成功", "server_banner": banner},
        }
    except ForbiddenError:
        raise
    except paramiko.AuthenticationException as exc:
        raise ValidationError("SSH 认证失败，请检查用户名和密码") from exc
    except Exception as exc:  # noqa: BLE001 - 统一转换为可读错误
        raise ValidationError(f"SSH 连接失败: {exc}") from exc
    finally:
        if client is not None:
            client.close()
        _write_ssh_audit(
            db=db,
            current_user=current_user,
            action="ssh.test",
            req=req,
            result=audit_result,
            result_code=result_code,
        )


@router.post("/ssh/request", response_model=dict[str, Any])
def execute_request(
    req: SSHCurlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """通过 SSH 在远程服务器执行一条由结构化参数生成的 curl 请求."""
    audit_result = "failed"
    result_code: int | None = None
    client: _SSHClient | None = None
    try:
        # 后端权威闸：首个执行语句，未启用时直接 403（仍写 1 条失败审计）。
        _require_console_enabled()
        command = build_curl_command(req)
        started = time.perf_counter()
        client = _SSHClient(req, req.timeout)
        client.connect()
        exit_code, stdout, stderr, truncated = client.run(command, _MAX_OUTPUT_BYTES)
        audit_result = "success"
        result_code = exit_code
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
    except ForbiddenError:
        raise
    except ValidationError:
        raise
    except paramiko.AuthenticationException as exc:
        raise ValidationError("SSH 认证失败，请检查用户名和密码") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"SSH 执行失败: {exc}") from exc
    finally:
        if client is not None:
            client.close()
        _write_ssh_audit(
            db=db,
            current_user=current_user,
            action="ssh.request",
            req=req,
            result=audit_result,
            result_code=result_code,
        )


# ---------- 保存的接口 ----------

def _serialize(item: ServerSavedRequest) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "method": item.method,
        "url": item.url,
        "params": item.params or {},
        "headers": item.headers or {},
        "body": item.body,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _get_owned_or_404(
    db: Session, request_id: str, current_user: User
) -> ServerSavedRequest:
    item = db.get(ServerSavedRequest, request_id)
    if not item:
        raise NotFoundError("保存的接口", request_id)
    if item.created_by != current_user.id and not current_user.is_superuser:
        raise NotFoundError("保存的接口", request_id)
    return item


@router.get("/saved-requests", response_model=dict[str, Any])
def list_saved_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """列出当前用户保存的接口."""
    items = (
        db.execute(
            select(ServerSavedRequest)
            .where(ServerSavedRequest.created_by == current_user.id)
            .order_by(ServerSavedRequest.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return {"code": 0, "message": "ok", "data": [_serialize(item) for item in items]}


@router.post("/saved-requests", response_model=dict[str, Any])
def create_saved_request(
    payload: ServerSavedRequestInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """保存一条接口请求（不含服务器密码）."""
    _validate_headers(payload.headers)
    item = ServerSavedRequest(
        name=payload.name.strip(),
        method=payload.method,
        url=payload.url,
        params=payload.params,
        headers=payload.headers,
        body=payload.body,
        created_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"code": 0, "message": "已保存", "data": _serialize(item)}


@router.put("/saved-requests/{request_id}", response_model=dict[str, Any])
def update_saved_request(
    request_id: str,
    payload: ServerSavedRequestInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """更新已保存的接口."""
    item = _get_owned_or_404(db, request_id, current_user)
    _validate_headers(payload.headers)
    item.name = payload.name.strip()
    item.method = payload.method
    item.url = payload.url
    item.params = payload.params
    item.headers = payload.headers
    item.body = payload.body
    db.commit()
    db.refresh(item)
    return {"code": 0, "message": "已更新", "data": _serialize(item)}


@router.delete("/saved-requests/{request_id}", response_model=dict[str, Any])
def delete_saved_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """删除已保存的接口."""
    item = _get_owned_or_404(db, request_id, current_user)
    db.delete(item)
    db.commit()
    return {"code": 0, "message": "已删除", "data": {"id": request_id}}
