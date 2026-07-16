"""CI/CD 集成模块测试：API Token 认证、CLI 触发执行、Webhook 回调.

测试覆盖：
    - Token 创建、验证、吊销
    - Token 权限检查（scope 验证）
    - 触发执行（通过 plan_id 和 case_ids）
    - Webhook 注册、签名验证
    - Webhook 发送（mock httpx）

由于本模块路由未在 main.py 中注册（集成阶段由主 agent 统一处理），
测试通过自行构建 FastAPI 应用并挂载本模块路由来验证 HTTP 行为。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import app.models  # noqa: F401  注册既有模型元数据
import app.models.api_token  # noqa: F401  注册 ApiToken
import app.models.webhook_config  # noqa: F401  注册 WebhookConfig

# role.py 尚未在 models/__init__.py 中注册（集成阶段由主 agent 处理），
# 此处显式导入以使 User mapper 的 user_roles 关联可解析，避免 mapper 初始化失败。
import app.models.role  # noqa: F401
from app.core.exceptions import AppException
from app.database import get_db
from app.models.user import User
from app.schemas.execution import (
    AssertionResult,
    ExecutionResult,
    ResponseData,
)


# ---------------------------------------------------------------------------
# 测试辅助：构建挂载了 CI/CD 路由的 FastAPI 应用与 TestClient
# ---------------------------------------------------------------------------


def _make_client(db_session):
    """构建挂载 api_tokens 与 ci_cd 路由的 TestClient，复用同一 db_session."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from app.api.v1.api_tokens import router as api_tokens_router
    from app.api.v1.ci_cd import router as ci_cd_router
    from app.services.auth_service import get_current_user

    app = FastAPI()

    @app.exception_handler(AppException)
    async def _handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": -1, "message": exc.message, "detail": exc.detail},
        )

    app.include_router(api_tokens_router, prefix="/api/v1/api-tokens")
    app.include_router(ci_cd_router, prefix="/api/v1/ci")

    def _override():
        yield db_session

    def _override_user():
        return User(
            id="ci-test-admin",
            username="ci-test-admin",
            email="ci-test-admin@test.local",
            hashed_password="",
            is_active=True,
            is_superuser=True,
        )

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_current_user] = _override_user
    return TestClient(app)


def _make_result(test_case_id: str = "", status: str = "passed") -> ExecutionResult:
    """构造 ExecutionResult 用于 mock 执行器."""
    return ExecutionResult(
        test_case_id=test_case_id,
        status=status,
        duration=0.01,
        request=None,
        response=ResponseData(status_code=200, headers={}, body={"ok": True}, elapsed=0.01, text='{"ok": true}'),
        assertion_results=[
            AssertionResult(
                assertion_type="status_code",
                operator="eq",
                expected="200",
                actual=200,
                passed=True,
            )
        ],
        extracted_variables=[],
        executed_at=datetime.now(),
    )


def _create_case_orm(db, title="CI用例", url="http://localhost/x", method="GET"):
    """直接通过 ORM 创建测试用例."""
    from app.models import TestCase

    case = TestCase(title=title, method=method, url=url)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def _create_plan_orm(db, case_ids, name="CI计划"):
    """直接通过 ORM 创建测试计划及计划项."""
    from app.models import TestPlan, TestPlanItem

    plan = TestPlan(name=name, execution_mode="sequential")
    db.add(plan)
    db.flush()
    for i, cid in enumerate(case_ids):
        db.add(TestPlanItem(plan_id=plan.id, test_case_id=cid, order=i + 1))
    db.commit()
    db.refresh(plan)
    return plan


# ---------------------------------------------------------------------------
# Token 服务：创建 / 验证 / 吊销
# ---------------------------------------------------------------------------


class TestTokenService:
    def test_create_token_returns_plaintext_with_prefix(self, db_session):
        from app.services.ci_cd_service import create_token

        record, plaintext = create_token(db_session, name="ci-token", scopes=["test-cases:execute"])
        assert record.id
        assert record.name == "ci-token"
        # 明文 token 带 air_ 前缀
        assert plaintext.startswith("air_")
        # SEC-03: 数据库存储的是 HMAC-SHA256 哈希值，不是明文
        assert record.token_hash != plaintext
        assert record.token_prefix == plaintext[:8]
        assert record.scopes == ["test-cases:execute"]
        assert record.is_active is True

    def test_create_token_uniqueness(self, db_session):
        from app.services.ci_cd_service import create_token

        _, t1 = create_token(db_session, name="a", scopes=[])
        _, t2 = create_token(db_session, name="b", scopes=[])
        assert t1 != t2

    def test_validate_token_success(self, db_session):
        from app.services.ci_cd_service import create_token, validate_token

        record, plaintext = create_token(db_session, name="t", scopes=["test-cases:execute", "test-plans:execute"])
        validated = validate_token(db_session, plaintext)
        assert validated.id == record.id
        # 验证后 last_used_at 应被更新
        assert validated.last_used_at is not None

    def test_validate_token_invalid(self, db_session):
        from app.services.ci_cd_service import validate_token
        from app.core.exceptions import AuthenticationError

        try:
            validate_token(db_session, "air_does_not_exist")
            assert False, "应抛出认证异常"
        except AuthenticationError:
            pass

    def test_validate_token_revoked(self, db_session):
        from app.services.ci_cd_service import create_token, validate_token
        from app.core.exceptions import AuthenticationError

        record, plaintext = create_token(db_session, name="t", scopes=[])
        record.is_active = False
        db_session.commit()
        try:
            validate_token(db_session, plaintext)
            assert False, "吊销后的 token 不应通过验证"
        except AuthenticationError:
            pass

    def test_validate_token_expired(self, db_session):
        from app.services.ci_cd_service import create_token, validate_token
        from app.core.exceptions import AuthenticationError

        record, plaintext = create_token(
            db_session, name="t", scopes=[], expires_at=datetime.now() - timedelta(hours=1)
        )
        try:
            validate_token(db_session, plaintext)
            assert False, "过期 token 不应通过验证"
        except AuthenticationError:
            pass

    def test_validate_token_scope_check(self, db_session):
        from app.services.ci_cd_service import create_token, validate_token
        from app.core.exceptions import AuthenticationError

        _, plaintext = create_token(db_session, name="t", scopes=["test-cases:execute"])
        # 拥有的 scope 通过
        validated = validate_token(db_session, plaintext, required_scope="test-cases:execute")
        assert validated is not None
        # 未拥有的 scope 失败
        try:
            validate_token(db_session, plaintext, required_scope="test-plans:execute")
            assert False, "缺少 scope 应抛出认证异常"
        except AuthenticationError:
            pass

    def test_revoke_token(self, db_session):
        from app.services.ci_cd_service import create_token, revoke_token

        record, _ = create_token(db_session, name="t", scopes=[])
        revoke_token(db_session, record.id)
        db_session.expire_all()
        gone = db_session.get(type(record), record.id)
        assert gone is None


# ---------------------------------------------------------------------------
# 触发执行服务（mock 执行器）
# ---------------------------------------------------------------------------


class TestTriggerExecution:
    def test_trigger_by_case_ids(self, db_session):
        from app.services.ci_cd_service import trigger_execution

        c1 = _create_case_orm(db_session, title="A")
        c2 = _create_case_orm(db_session, title="B")

        with patch("app.services.ci_cd_service._ci_executor") as mock_exec:
            mock_exec.execute.side_effect = lambda **kw: _make_result(
                test_case_id=kw.get("test_case_id", ""), status="passed"
            )
            result = trigger_execution(db_session, case_ids=[c1.id, c2.id], source="ci")

        assert result["run_id"]
        assert result["total"] == 2
        assert result["passed"] == 2
        assert result["failed"] == 0
        assert result["error"] == 0
        assert result["status"] == "passed"
        # 应创建 TestRunSummary 且 source 为 ci
        from app.models import TestRunSummary

        summary = db_session.query(TestRunSummary).filter(TestRunSummary.run_id == result["run_id"]).first()
        assert summary is not None
        assert summary.source == "ci"
        assert summary.total == 2

    def test_trigger_by_plan_id(self, db_session):
        from app.services.ci_cd_service import trigger_execution

        c1 = _create_case_orm(db_session, title="P1")
        c2 = _create_case_orm(db_session, title="P2")
        plan = _create_plan_orm(db_session, [c1.id, c2.id])

        with patch("app.services.ci_cd_service._ci_executor") as mock_exec:
            mock_exec.execute.side_effect = lambda **kw: _make_result(
                test_case_id=kw.get("test_case_id", ""), status="passed"
            )
            result = trigger_execution(db_session, plan_id=plan.id, source="ci")

        assert result["total"] == 2
        assert result["passed"] == 2
        assert result["status"] == "passed"

    def test_trigger_records_failure_status(self, db_session):
        from app.services.ci_cd_service import trigger_execution

        c1 = _create_case_orm(db_session, title="F")
        with patch("app.services.ci_cd_service._ci_executor") as mock_exec:
            mock_exec.execute.return_value = _make_result(test_case_id=c1.id, status="failed")
            result = trigger_execution(db_session, case_ids=[c1.id], source="ci")

        assert result["failed"] == 1
        assert result["status"] == "failed"

    def test_trigger_plan_not_found(self, db_session):
        from app.services.ci_cd_service import trigger_execution
        from app.core.exceptions import NotFoundError

        try:
            trigger_execution(db_session, plan_id="nope", source="ci")
            assert False, "不存在的计划应抛出 404"
        except NotFoundError:
            pass


# ---------------------------------------------------------------------------
# Webhook 签名与发送
# ---------------------------------------------------------------------------


class TestWebhookSignature:
    def test_sign_payload_hmac_sha256(self):
        import hashlib
        import hmac

        from app.services.ci_cd_service import sign_payload

        secret = "wh-secret"
        body = b'{"event":"test_run.completed"}'
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        assert sign_payload(secret, body) == expected

    def test_sign_payload_accepts_str(self):
        import hashlib
        import hmac

        from app.services.ci_cd_service import sign_payload

        secret = "s"
        text = "hello"
        expected = hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()
        assert sign_payload(secret, text) == expected


class TestWebhookSend:
    def test_send_webhook_posts_with_signature(self, db_session):
        from app.models.webhook_config import WebhookConfig
        from app.services.ci_cd_service import send_webhook, sign_payload

        cfg = WebhookConfig(
            name="ci-hook",
            url="https://example.com/hook",
            events=["test_run.completed", "test_run.failed"],
            secret="wh-secret",
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()

        payload = {"run_id": "r1", "status": "passed"}
        with patch("app.services.ci_cd_service.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.is_success = True
            mock_httpx.post.return_value = mock_resp

            results = send_webhook(db_session, "test_run.completed", payload)

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["status_code"] == 200
        # 验证 httpx.post 被调用，且带签名头
        mock_httpx.post.assert_called_once()
        _, kwargs = mock_httpx.post.call_args
        headers = kwargs["headers"]
        assert "X-Airetest-Signature" in headers
        # 签名应与 sign_payload 计算一致
        sent_body = kwargs["content"]
        assert headers["X-Airetest-Signature"] == sign_payload("wh-secret", sent_body)
        assert headers["X-Airetest-Event"] == "test_run.completed"

    def test_send_webhook_skips_inactive_and_unmatched(self, db_session):
        from app.models.webhook_config import WebhookConfig
        from app.services.ci_cd_service import send_webhook

        # 不匹配事件
        db_session.add(
            WebhookConfig(
                name="a",
                url="https://e.com/1",
                events=["test_run.failed"],
                secret="s",
                is_active=True,
            )
        )
        # 已禁用但事件匹配
        db_session.add(
            WebhookConfig(
                name="b",
                url="https://e.com/2",
                events=["test_run.completed"],
                secret="s",
                is_active=False,
            )
        )
        db_session.commit()

        with patch("app.services.ci_cd_service.httpx") as mock_httpx:
            mock_resp = MagicMock(status_code=200, is_success=True)
            mock_httpx.post.return_value = mock_resp
            results = send_webhook(db_session, "test_run.completed", {"r": 1})

        # 两个 webhook 都不应被发送
        assert results == []
        mock_httpx.post.assert_not_called()

    def test_send_webhook_handles_request_error(self, db_session):
        from app.models.webhook_config import WebhookConfig
        from app.services.ci_cd_service import send_webhook

        db_session.add(
            WebhookConfig(
                name="bad",
                url="https://e.com/x",
                events=["test_run.completed"],
                secret="s",
                is_active=True,
            )
        )
        db_session.commit()

        with patch("app.services.ci_cd_service.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("connection refused")
            results = send_webhook(db_session, "test_run.completed", {"r": 1})

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "connection refused" in results[0]["error"]


# ---------------------------------------------------------------------------
# HTTP：API Token 管理
# ---------------------------------------------------------------------------


class TestApiTokenHttp:
    def test_create_returns_plaintext_once(self, db_session):
        client = _make_client(db_session)
        resp = client.post(
            "/api/v1/api-tokens",
            json={"name": "ci", "scopes": ["test-cases:execute"]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["token"].startswith("air_")
        assert data["name"] == "ci"
        assert data["scopes"] == ["test-cases:execute"]
        # 同时给出脱敏字段
        assert data["token_masked"]
        assert data["token_masked"] != data["token"]

    def test_list_returns_masked_only(self, db_session):
        client = _make_client(db_session)
        create_resp = client.post(
            "/api/v1/api-tokens",
            json={"name": "t1", "scopes": ["test-plans:execute"]},
        )
        plaintext = create_resp.json()["data"]["token"]

        resp = client.get("/api/v1/api-tokens")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert len(body["data"]) == 1
        item = body["data"][0]
        # 列表不返回明文 token
        assert "token" not in item
        assert item["token_masked"]
        assert plaintext not in item["token_masked"]
        assert item["name"] == "t1"

    def test_delete_revokes_token(self, db_session):
        client = _make_client(db_session)
        create_resp = client.post("/api/v1/api-tokens", json={"name": "t", "scopes": []})
        token_id = create_resp.json()["data"]["id"]

        del_resp = client.delete(f"/api/v1/api-tokens/{token_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["code"] == 0

        # 列表中不再存在
        list_resp = client.get("/api/v1/api-tokens").json()
        assert len(list_resp["data"]) == 0

    def test_delete_not_found(self, db_session):
        client = _make_client(db_session)
        resp = client.delete("/api/v1/api-tokens/nope")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# HTTP：Webhook CRUD + 测试
# ---------------------------------------------------------------------------


class TestWebhookHttp:
    def test_create_and_list(self, db_session):
        client = _make_client(db_session)
        resp = client.post(
            "/api/v1/ci/webhooks",
            json={
                "name": "ci-hook",
                "url": "https://example.com/hook",
                "events": ["test_run.completed"],
                "secret": "s",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["id"]
        assert data["url"] == "****"
        assert data["has_url"] is True
        # 不返回明文 secret
        assert "secret" not in data
        assert data["has_secret"] is True

        list_resp = client.get("/api/v1/ci/webhooks")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["data"]) == 1

    def test_update(self, db_session):
        client = _make_client(db_session)
        create = client.post(
            "/api/v1/ci/webhooks",
            json={"name": "h", "url": "https://e.com", "events": ["test_run.failed"], "secret": "s"},
        )
        wid = create.json()["data"]["id"]
        resp = client.put(
            f"/api/v1/ci/webhooks/{wid}",
            json={"name": "h2", "events": ["test_run.completed", "test_run.failed"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "h2"
        assert "test_run.completed" in data["events"]

    def test_delete(self, db_session):
        client = _make_client(db_session)
        create = client.post(
            "/api/v1/ci/webhooks",
            json={"name": "h", "url": "https://e.com", "events": ["x"], "secret": "s"},
        )
        wid = create.json()["data"]["id"]
        assert client.delete(f"/api/v1/ci/webhooks/{wid}").status_code == 200
        assert client.get("/api/v1/ci/webhooks").json()["data"] == []

    def test_test_endpoint(self, db_session):
        client = _make_client(db_session)
        create = client.post(
            "/api/v1/ci/webhooks",
            json={"name": "h", "url": "https://e.com", "events": ["test_run.completed"], "secret": "s"},
        )
        wid = create.json()["data"]["id"]

        with patch("app.api.v1.ci_cd.send_webhook") as mock_send:
            mock_send.return_value = [{"webhook_id": wid, "url": "https://e.com", "status_code": 200, "success": True}]
            resp = client.post(f"/api/v1/ci/webhooks/{wid}/test")

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["sent"] is True
        assert data["results"][0]["success"] is True


# ---------------------------------------------------------------------------
# HTTP：CI 触发（API Token 认证）
# ---------------------------------------------------------------------------


class TestCiTriggerHttp:
    def _make_token(self, db_session, scopes):
        from app.services.ci_cd_service import create_token

        _, plaintext = create_token(db_session, name="ci", scopes=scopes)
        return plaintext

    def test_trigger_by_case_ids_with_token(self, db_session):
        client = _make_client(db_session)
        c1 = _create_case_orm(db_session, title="A")
        token = self._make_token(db_session, ["test-cases:execute"])

        with patch("app.services.ci_cd_service._ci_executor") as mock_exec, patch("app.api.v1.ci_cd._notify_webhooks"):
            mock_exec.execute.return_value = _make_result(test_case_id=c1.id, status="passed")
            resp = client.post(
                "/api/v1/ci/trigger",
                json={"case_ids": [c1.id]},
                headers={"X-API-Key": token},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["run_id"]
        assert data["status"] == "passed"
        assert data["total"] == 1
        assert data["passed"] == 1

    def test_trigger_by_plan_id_with_bearer(self, db_session):
        client = _make_client(db_session)
        c1 = _create_case_orm(db_session, title="A")
        plan = _create_plan_orm(db_session, [c1.id])
        token = self._make_token(db_session, ["test-plans:execute"])

        with patch("app.services.ci_cd_service._ci_executor") as mock_exec, patch("app.api.v1.ci_cd._notify_webhooks"):
            mock_exec.execute.return_value = _make_result(test_case_id=c1.id, status="passed")
            resp = client.post(
                "/api/v1/ci/trigger",
                json={"plan_id": plan.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "passed"

    def test_trigger_without_token_unauthorized(self, db_session):
        client = _make_client(db_session)
        c1 = _create_case_orm(db_session, title="A")
        resp = client.post("/api/v1/ci/trigger", json={"case_ids": [c1.id]})
        assert resp.status_code == 401

    def test_trigger_missing_scope_forbidden(self, db_session):
        client = _make_client(db_session)
        c1 = _create_case_orm(db_session, title="A")
        # token 仅有 test-cases:execute，却用 plan_id 触发
        plan = _create_plan_orm(db_session, [c1.id])
        token = self._make_token(db_session, ["test-cases:execute"])

        resp = client.post(
            "/api/v1/ci/trigger",
            json={"plan_id": plan.id},
            headers={"X-API-Key": token},
        )
        assert resp.status_code == 401

    def test_trigger_invalid_token_unauthorized(self, db_session):
        client = _make_client(db_session)
        resp = client.post(
            "/api/v1/ci/trigger",
            json={"case_ids": ["x"]},
            headers={"X-API-Key": "air_invalid"},
        )
        assert resp.status_code == 401

    def test_run_status(self, db_session):
        client = _make_client(db_session)
        c1 = _create_case_orm(db_session, title="A")
        token = self._make_token(db_session, ["test-cases:execute"])

        with patch("app.services.ci_cd_service._ci_executor") as mock_exec, patch("app.api.v1.ci_cd._notify_webhooks"):
            mock_exec.execute.return_value = _make_result(test_case_id=c1.id, status="passed")
            trig = client.post(
                "/api/v1/ci/trigger",
                json={"case_ids": [c1.id]},
                headers={"X-API-Key": token},
            )
        run_id = trig.json()["data"]["run_id"]

        resp = client.get(f"/api/v1/ci/runs/{run_id}/status")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["run_id"] == run_id
        assert data["total"] == 1
        assert data["source"] == "ci"

    def test_run_status_not_found(self, db_session):
        client = _make_client(db_session)
        resp = client.get("/api/v1/ci/runs/nope/status")
        assert resp.status_code == 404
