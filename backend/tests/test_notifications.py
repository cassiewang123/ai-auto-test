"""通知模块测试：渠道/规则 CRUD、消息格式化、加签、发送（mock httpx）."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship as _relationship

# 注册所有 ORM 模型（含通知模块），确保 Base.metadata.create_all 建表
import app.models  # noqa: F401
from app.models.notification_channel import NotificationChannel  # noqa: F401
from app.models.notification_log import NotificationLog  # noqa: F401
from app.models.notification_rule import NotificationRule  # noqa: F401
from app.database import Base, get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services import notification_service as ns

# ---------------------------------------------------------------------------
# 测试专用补丁：预存的 User 模型引用了未定义的 Role 类与 user_roles 表，
# 导致 SQLAlchemy 全局 mapper 配置失败（影响所有涉及 DB 的 API 测试）。
# 此处仅用于测试环境补全缺失定义，不修改任何共享源文件。
# ---------------------------------------------------------------------------
if "roles" not in Base.metadata.tables:

    class Role(Base):  # noqa: F811
        __tablename__ = "roles"
        id: Mapped[str] = mapped_column(
            String(36), primary_key=True, default=lambda: str(uuid.uuid4())
        )
        name: Mapped[str] = mapped_column(String(64))
        users: Mapped[list["User"]] = _relationship(
            secondary="user_roles", back_populates="roles"
        )

    Table(
        "user_roles",
        Base.metadata,
        Column("user_id", String(36), ForeignKey("users.id"), primary_key=True),
        Column("role_id", String(36), ForeignKey("roles.id"), primary_key=True),
    )

BASE = "/api/v1/notifications"


# ---------------------------------------------------------------------------
# 自定义 client fixture：在 create_app 基础上注册通知路由
# （main.py 由集成阶段统一修改，此处不改动共享文件）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def client(db_session):
    from app.api.v1.notifications import router as notifications_router
    from app.main import create_app

    app = create_app()
    app.include_router(notifications_router, prefix=f"/api/v1/notifications")

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: User(
        id="notification-test-admin",
        username="notification-test-admin",
        email="notification-test-admin@test.local",
        hashed_password="",
        is_active=True,
        is_superuser=True,
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _create_channel(client, **overrides):
    payload = {
        "name": "飞书通知",
        "type": "feishu",
        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        "secret": "SEC123",
    }
    payload.update(overrides)
    resp = client.post(f"{BASE}/channels", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _create_rule(client, channel_id, **overrides):
    payload = {
        "name": "测试完成通知",
        "channel_id": channel_id,
        "event_type": "test_run.completed",
    }
    payload.update(overrides)
    resp = client.post(f"{BASE}/rules", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _make_post_mock(status_code=200, text='{"code":0}'):
    """构造 httpx.AsyncClient 的 mock，返回 (patcher, post_mock)."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()

    client_mock = MagicMock()
    client_mock.post = AsyncMock(return_value=resp)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client_mock)
    cm.__aexit__ = AsyncMock(return_value=None)

    patcher = patch(
        "app.services.notification_service.httpx.AsyncClient",
        return_value=cm,
    )
    return patcher, client_mock.post


# ===========================================================================
# 渠道 CRUD
# ===========================================================================
class TestChannelCRUD:
    def test_create_success(self, client):
        data = _create_channel(client, name="钉钉机器人", type="dingtalk")
        assert data["id"]
        assert data["name"] == "钉钉机器人"
        assert data["type"] == "dingtalk"
        assert data["is_active"] is True
        # SEC-08: 响应不返回明文 secret，仅返回 has_secret 标记
        assert "secret" not in data
        assert data["has_secret"] is True

    def test_create_invalid_type(self, client):
        resp = client.post(
            f"{BASE}/channels",
            json={"name": "x", "type": "telegram", "webhook_url": "https://x"},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == -1

    def test_list_pagination(self, client):
        for i in range(3):
            _create_channel(client, name=f"ch-{i}", type="slack", secret=None)
        resp = client.get(f"{BASE}/channels?page=1&page_size=2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["data"]) == 2

    def test_list_filter_by_type(self, client):
        _create_channel(client, name="f1", type="feishu")
        _create_channel(client, name="s1", type="slack")
        resp = client.get(f"{BASE}/channels?type=slack")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["type"] == "slack"

    def test_list_search_by_name(self, client):
        _create_channel(client, name="prod-feishu", type="feishu")
        _create_channel(client, name="dev-slack", type="slack")
        resp = client.get(f"{BASE}/channels?name=prod")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["name"] == "prod-feishu"

    def test_update_success(self, client):
        ch = _create_channel(client, name="old")
        resp = client.put(
            f"{BASE}/channels/{ch['id']}",
            json={"name": "new", "is_active": False},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "new"
        assert data["is_active"] is False
        # 未更新字段保留
        assert data["type"] == "feishu"

    def test_update_not_found(self, client):
        resp = client.put(f"{BASE}/channels/nope", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete_success(self, client):
        ch = _create_channel(client, name="del")
        resp = client.delete(f"{BASE}/channels/{ch['id']}")
        assert resp.status_code == 200
        # 再次查询应不存在
        resp2 = client.get(f"{BASE}/channels")
        assert all(c["id"] != ch["id"] for c in resp2.json()["data"])

    def test_delete_not_found(self, client):
        resp = client.delete(f"{BASE}/channels/nope")
        assert resp.status_code == 404


# ===========================================================================
# 规则 CRUD
# ===========================================================================
class TestRuleCRUD:
    def test_create_success(self, client):
        ch = _create_channel(client, secret=None)
        data = _create_rule(client, ch["id"], event_type="test_run.failed")
        assert data["id"]
        assert data["channel_id"] == ch["id"]
        assert data["event_type"] == "test_run.failed"
        assert data["channel_name"] == "飞书通知"
        assert data["is_active"] is True

    def test_create_channel_not_found(self, client):
        resp = client.post(
            f"{BASE}/rules",
            json={"name": "r", "channel_id": "nope", "event_type": "x"},
        )
        assert resp.status_code == 404

    def test_create_with_filters(self, client):
        ch = _create_channel(client, secret=None)
        data = _create_rule(
            client,
            ch["id"],
            filters={"min_failure_rate": 0.1},
        )
        assert data["filters"] == {"min_failure_rate": 0.1}

    def test_list_rules(self, client):
        ch = _create_channel(client, secret=None)
        _create_rule(client, ch["id"], name="r1", event_type="test_run.completed")
        _create_rule(client, ch["id"], name="r2", event_type="test_run.failed")
        resp = client.get(f"{BASE}/rules")
        body = resp.json()
        assert body["total"] == 2

    def test_list_filter_by_event(self, client):
        ch = _create_channel(client, secret=None)
        _create_rule(client, ch["id"], event_type="test_run.completed")
        _create_rule(client, ch["id"], event_type="perf_test.completed")
        resp = client.get(f"{BASE}/rules?event_type=perf_test.completed")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["event_type"] == "perf_test.completed"

    def test_update_success(self, client):
        ch = _create_channel(client, secret=None)
        rule = _create_rule(client, ch["id"])
        resp = client.put(
            f"{BASE}/rules/{rule['id']}",
            json={"name": "updated", "is_active": False},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "updated"
        assert data["is_active"] is False

    def test_delete_success(self, client):
        ch = _create_channel(client, secret=None)
        rule = _create_rule(client, ch["id"])
        resp = client.delete(f"{BASE}/rules/{rule['id']}")
        assert resp.status_code == 200
        resp2 = client.get(f"{BASE}/rules")
        assert all(r["id"] != rule["id"] for r in resp2.json()["data"])

    def test_delete_channel_cascades_rules(self, client):
        """删除渠道应级联删除其规则."""
        ch = _create_channel(client, secret=None)
        _create_rule(client, ch["id"])
        resp = client.delete(f"{BASE}/channels/{ch['id']}")
        assert resp.status_code == 200
        resp2 = client.get(f"{BASE}/rules")
        assert resp2.json()["total"] == 0


# ===========================================================================
# 消息内容格式化
# ===========================================================================
class TestFormatMessage:
    def test_test_run_completed(self):
        msg = ns.format_message(
            "test_run.completed",
            {"total": 10, "passed": 8, "failed": 2, "duration": 5.5},
        )
        assert msg == "测试执行完成 | 总数:10 通过:8 失败:2 耗时:5.5s"

    def test_test_run_failed(self):
        msg = ns.format_message(
            "test_run.failed", {"failed": 3, "error": 1}
        )
        assert msg == "测试执行失败 | 失败:3 错误:1"

    def test_scheduled_task_completed(self):
        msg = ns.format_message(
            "scheduled_task.completed",
            {"task_name": "daily", "pass_rate": 95},
        )
        assert msg == "定时任务[daily]执行完成 | 通过率:95%"

    def test_perf_test_completed(self):
        msg = ns.format_message(
            "perf_test.completed",
            {"rps": 100, "p95": 200, "error_rate": 0.5},
        )
        assert msg == "性能测试完成 | RPS:100 P95:200ms 错误率:0.5%"

    def test_unknown_event(self):
        msg = ns.format_message("unknown.event", {"message": "hello"})
        assert msg == "hello"

    def test_unknown_event_no_message(self):
        msg = ns.format_message("unknown.event", {})
        assert "unknown.event" in msg

    def test_missing_context_keys_use_defaults(self):
        """上下文缺失键时使用默认值 0."""
        msg = ns.format_message("test_run.completed", {})
        assert "总数:0" in msg
        assert "通过:0" in msg


# ===========================================================================
# 加签
# ===========================================================================
class TestSigning:
    def test_gen_sign_known_value(self):
        secret = "test-secret"
        timestamp = "1700000000"
        string_to_sign = f"{timestamp}\n{secret}"
        expected = base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        assert ns.gen_sign(secret, timestamp) == expected

    def test_feishu_sign_equals_gen_sign(self):
        assert ns.gen_feishu_sign("s", "123") == ns.gen_sign("s", "123")

    def test_dingtalk_sign_equals_gen_sign(self):
        assert ns.gen_dingtalk_sign("s", "123") == ns.gen_sign("s", "123")

    def test_sign_deterministic(self):
        """相同输入产生相同签名."""
        s1 = ns.gen_sign("secret", "1700")
        s2 = ns.gen_sign("secret", "1700")
        assert s1 == s2

    def test_sign_changes_with_secret(self):
        assert ns.gen_sign("a", "1") != ns.gen_sign("b", "1")

    def test_sign_changes_with_timestamp(self):
        assert ns.gen_sign("a", "1") != ns.gen_sign("a", "2")


# ===========================================================================
# 发送函数（mock httpx）
# ===========================================================================
class TestSendFeishu:
    def test_send_without_secret(self):
        patcher, post_mock = _make_post_mock()
        with patcher:
            result = asyncio.run(
                ns.send_feishu("https://hook.feishu", None, "标题", "内容")
            )
        assert result["ok"] is True
        post_mock.assert_called_once()
        url = post_mock.call_args.args[0]
        payload = post_mock.call_args.kwargs["json"]
        assert url == "https://hook.feishu"
        assert payload["msg_type"] == "text"
        assert "标题" in payload["content"]["text"]
        assert "内容" in payload["content"]["text"]
        # 无 secret 时不应包含 timestamp/sign
        assert "timestamp" not in payload
        assert "sign" not in payload

    def test_send_with_secret(self):
        patcher, post_mock = _make_post_mock()
        with patcher:
            asyncio.run(
                ns.send_feishu("https://hook.feishu", "SEC", "标题", "内容")
            )
        payload = post_mock.call_args.kwargs["json"]
        assert "timestamp" in payload
        assert "sign" in payload
        # 验证签名正确
        expected_sign = ns.gen_feishu_sign("SEC", payload["timestamp"])
        assert payload["sign"] == expected_sign

    def test_send_raises_on_http_error(self):
        patcher, post_mock = _make_post_mock()
        post_mock.side_effect = Exception("network error")
        with patcher:
            with pytest.raises(Exception, match="network error"):
                asyncio.run(
                    ns.send_feishu("https://hook", None, "t", "c")
                )


class TestSendDingtalk:
    def test_send_without_secret(self):
        patcher, post_mock = _make_post_mock()
        with patcher:
            asyncio.run(
                ns.send_dingtalk(
                    "https://oapi.dingtalk.com/robot/send?access_token=abc",
                    None,
                    "标题",
                    "内容",
                )
            )
        url = post_mock.call_args.args[0]
        payload = post_mock.call_args.kwargs["json"]
        assert "access_token=abc" in url
        assert "timestamp" not in url
        assert payload["msgtype"] == "text"
        assert "标题" in payload["text"]["content"]
        assert "内容" in payload["text"]["content"]

    def test_send_with_secret(self):
        patcher, post_mock = _make_post_mock()
        with patcher:
            asyncio.run(
                ns.send_dingtalk(
                    "https://oapi.dingtalk.com/robot/send?access_token=abc",
                    "SEC",
                    "标题",
                    "内容",
                )
            )
        url = post_mock.call_args.args[0]
        assert "timestamp=" in url
        assert "sign=" in url
        assert "access_token=abc" in url
        # 验证签名在 URL 中
        # 提取 timestamp
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(url).query)
        assert "timestamp" in qs
        assert "sign" in qs
        expected_sign = ns.gen_dingtalk_sign("SEC", qs["timestamp"][0])
        assert qs["sign"][0] == expected_sign


class TestSendWechat:
    def test_send_payload(self):
        patcher, post_mock = _make_post_mock()
        with patcher:
            asyncio.run(
                ns.send_wechat(
                    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x",
                    "标题",
                    "内容",
                )
            )
        url = post_mock.call_args.args[0]
        payload = post_mock.call_args.kwargs["json"]
        assert url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x"
        assert payload["msgtype"] == "text"
        assert "标题" in payload["text"]["content"]
        assert "内容" in payload["text"]["content"]


class TestSendSlack:
    def test_send_payload(self):
        patcher, post_mock = _make_post_mock()
        with patcher:
            asyncio.run(
                ns.send_slack(
                    "https://hooks.slack.com/services/x",
                    "标题",
                    "内容",
                )
            )
        url = post_mock.call_args.args[0]
        payload = post_mock.call_args.kwargs["json"]
        assert url == "https://hooks.slack.com/services/x"
        assert "text" in payload
        assert "标题" in payload["text"]
        assert "内容" in payload["text"]


# ===========================================================================
# 统一发送入口 send_notification
# ===========================================================================
class _FakeChannel:
    """模拟渠道对象."""

    def __init__(self, type, webhook_url, secret=None, name="ch"):
        self.type = type
        self.webhook_url = webhook_url
        self.secret = secret
        self.name = name


class TestSendNotification:
    def test_dispatch_feishu(self):
        patcher, post_mock = _make_post_mock()
        ch = _FakeChannel("feishu", "https://hook.feishu", "SEC")
        with patcher:
            result = asyncio.run(
                ns.send_notification(ch, "test_run.completed",
                                     {"total": 10, "passed": 8, "failed": 2, "duration": 5})
            )
        assert result["success"] is True
        assert "总数:10" in result["message"]
        post_mock.assert_called_once()
        # 飞书带 secret，payload 应含 sign
        payload = post_mock.call_args.kwargs["json"]
        assert "sign" in payload

    def test_dispatch_dingtalk(self):
        patcher, post_mock = _make_post_mock()
        ch = _FakeChannel(
            "dingtalk", "https://oapi.dingtalk.com/robot/send?access_token=x", "SEC"
        )
        with patcher:
            result = asyncio.run(
                ns.send_notification(ch, "test_run.failed",
                                     {"failed": 3, "error": 1})
            )
        assert result["success"] is True
        assert "失败:3" in result["message"]
        url = post_mock.call_args.args[0]
        assert "sign=" in url

    def test_dispatch_wechat(self):
        patcher, post_mock = _make_post_mock()
        ch = _FakeChannel("wechat", "https://qyapi.weixin.qq.com/key=x")
        with patcher:
            result = asyncio.run(
                ns.send_notification(ch, "scheduled_task.completed",
                                     {"task_name": "daily", "pass_rate": 95})
            )
        assert result["success"] is True
        assert "定时任务[daily]" in result["message"]

    def test_dispatch_slack(self):
        patcher, post_mock = _make_post_mock()
        ch = _FakeChannel("slack", "https://hooks.slack.com/x")
        with patcher:
            result = asyncio.run(
                ns.send_notification(ch, "perf_test.completed",
                                     {"rps": 100, "p95": 200, "error_rate": 0.5})
            )
        assert result["success"] is True
        assert "RPS:100" in result["message"]

    def test_unsupported_type(self):
        ch = _FakeChannel("telegram", "https://x")
        result = asyncio.run(ns.send_notification(ch, "test_run.completed", {}))
        assert result["success"] is False
        assert "不支持" in result["message"]

    def test_failure_does_not_raise(self):
        """发送失败时返回失败信息而非抛异常."""
        patcher, post_mock = _make_post_mock()
        post_mock.side_effect = Exception("connection refused")
        ch = _FakeChannel("feishu", "https://hook.feishu")
        with patcher:
            result = asyncio.run(
                ns.send_notification(ch, "test_run.completed", {"total": 1})
            )
        assert result["success"] is False
        assert "connection refused" in result["message"]


# ===========================================================================
# 测试通知 API（端到端，mock httpx）
# ===========================================================================
class TestTestNotificationEndpoint:
    def test_test_success(self, client):
        ch = _create_channel(client, type="slack", secret=None)
        patcher, _ = _make_post_mock()
        with patcher:
            resp = client.post(f"{BASE}/channels/{ch['id']}/test")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["success"] is True
        assert body["status"] == "success"
        assert "测试通知" in body["message"]

    def test_test_with_custom_content(self, client):
        ch = _create_channel(client, type="slack", secret=None)
        patcher, _ = _make_post_mock()
        with patcher:
            resp = client.post(
                f"{BASE}/channels/{ch['id']}/test",
                json={"content": "自定义测试内容"},
            )
        body = resp.json()["data"]
        assert body["success"] is True
        assert body["message"] == "自定义测试内容"

    def test_test_failure_logs_failed(self, client):
        ch = _create_channel(client, type="feishu", secret=None)
        patcher, post_mock = _make_post_mock()
        post_mock.side_effect = Exception("timeout")
        with patcher:
            resp = client.post(f"{BASE}/channels/{ch['id']}/test")
        body = resp.json()["data"]
        assert body["success"] is False
        assert body["status"] == "failed"
        assert "timeout" in body["message"]
        # 验证日志已记录
        resp2 = client.get(f"{BASE}/logs")
        logs = resp2.json()["data"]
        assert any(l["status"] == "failed" for l in logs)

    def test_test_not_found(self, client):
        resp = client.post(f"{BASE}/channels/nope/test")
        assert resp.status_code == 404


# ===========================================================================
# 日志查询
# ===========================================================================
class TestLogs:
    def test_list_empty(self, client):
        resp = client.get(f"{BASE}/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["data"] == []

    def test_list_after_test(self, client):
        ch = _create_channel(client, type="slack", secret=None)
        patcher, _ = _make_post_mock()
        with patcher:
            client.post(f"{BASE}/channels/{ch['id']}/test")
        resp = client.get(f"{BASE}/logs")
        body = resp.json()
        assert body["total"] == 1
        log = body["data"][0]
        assert log["channel_name"] == "飞书通知"
        assert log["event_type"] == "test"
        assert log["status"] == "success"

    def test_filter_by_status(self, client):
        ch = _create_channel(client, type="slack", secret=None)
        patcher, post_mock = _make_post_mock()
        with patcher:
            client.post(f"{BASE}/channels/{ch['id']}/test")
            post_mock.side_effect = Exception("err")
            client.post(f"{BASE}/channels/{ch['id']}/test")
        resp = client.get(f"{BASE}/logs?status=failed")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["status"] == "failed"

    def test_filter_by_channel(self, client):
        ch1 = _create_channel(client, name="c1", type="slack", secret=None)
        ch2 = _create_channel(client, name="c2", type="slack", secret=None)
        patcher, _ = _make_post_mock()
        with patcher:
            client.post(f"{BASE}/channels/{ch1['id']}/test")
            client.post(f"{BASE}/channels/{ch2['id']}/test")
            client.post(f"{BASE}/channels/{ch1['id']}/test")
        resp = client.get(f"{BASE}/logs?channel_id={ch1['id']}")
        body = resp.json()
        assert body["total"] == 2
