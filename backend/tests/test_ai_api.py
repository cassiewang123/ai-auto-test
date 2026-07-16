"""AI API 路由测试。

使用 conftest 的 client fixture 测试各端点返回格式正确。
默认走 fallback（无 API key），另通过依赖注入覆盖测试 LLM 路径。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.api.v1.ai import get_ai_service
from app.services.ai_service import AIService


# ---------------------------------------------------------------------------
# POST /api/v1/ai/generate-test-case
# ---------------------------------------------------------------------------
class TestGenerateTestCaseAPI:
    def test_basic(self, client):
        resp = client.post(
            "/api/v1/ai/generate-test-case",
            json={"description": "测试用户注册流程，覆盖正常注册、重复用户名、无效邮箱"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "data" in body
        assert "code" in body["data"]
        assert isinstance(body["data"]["code"], str)
        assert len(body["data"]["code"]) > 0

    def test_with_api_schema(self, client):
        resp = client.post(
            "/api/v1/ai/generate-test-case",
            json={
                "description": "创建用户",
                "api_schema": {"method": "POST", "path": "/api/v1/users"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_missing_description_returns_422(self, client):
        resp = client.post("/api/v1/ai/generate-test-case", json={})
        assert resp.status_code == 422

    def test_with_mocked_llm(self, client):
        """通过依赖注入覆盖 AIService，模拟 LLM 返回。"""
        mock_service = AIService()
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "import pytest\n\ndef test_generated():\n    assert True\n"
        mock_llm.invoke.return_value = mock_response
        mock_service._get_llm = lambda: mock_llm

        client.app.dependency_overrides[get_ai_service] = lambda: mock_service
        try:
            resp = client.post(
                "/api/v1/ai/generate-test-case",
                json={"description": "测试登录"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["code"] == 0
            assert "def test" in body["data"]["code"]
        finally:
            client.app.dependency_overrides.pop(get_ai_service, None)


# ---------------------------------------------------------------------------
# POST /api/v1/ai/recommend-assertions
# ---------------------------------------------------------------------------
class TestRecommendAssertionsAPI:
    def test_basic(self, client):
        resp = client.post(
            "/api/v1/ai/recommend-assertions",
            json={
                "response_sample": {
                    "code": 0,
                    "data": {"id": 1, "name": "test"},
                    "message": "ok",
                }
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "data" in body
        assert "assertions" in body["data"]
        assert isinstance(body["data"]["assertions"], list)
        assert len(body["data"]["assertions"]) > 0

    def test_returns_status_code_assertion(self, client):
        resp = client.post(
            "/api/v1/ai/recommend-assertions",
            json={"response_sample": {"id": 1}},
        )
        body = resp.json()
        types = [a["type"] for a in body["data"]["assertions"]]
        assert "status_code" in types
        assert "json_path" in types

    def test_missing_response_sample_returns_422(self, client):
        resp = client.post("/api/v1/ai/recommend-assertions", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/ai/analyze-failure
# ---------------------------------------------------------------------------
class TestAnalyzeFailureAPI:
    def test_basic(self, client):
        resp = client.post(
            "/api/v1/ai/analyze-failure",
            json={
                "test_case_id": "tc-1",
                "status": "failed",
                "duration": 1.5,
                "response": {"status_code": 500, "body": {}},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "data" in body
        data = body["data"]
        assert "root_cause" in data
        assert "evidence" in data
        assert "category" in data
        assert "suggestion" in data
        assert "confidence" in data

    def test_execution_error(self, client):
        resp = client.post(
            "/api/v1/ai/analyze-failure",
            json={
                "test_case_id": "tc-2",
                "status": "error",
                "error_message": "ConnectionRefusedError",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["category"] == "execution_error"

    def test_with_mocked_llm(self, client):
        """通过依赖注入覆盖 AIService，模拟 LLM 返回。"""
        mock_service = AIService()
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            '{"root_cause": "服务端异常", "evidence": "500", '
            '"category": "server_error", "suggestion": "查日志", "confidence": 0.9}'
        )
        mock_llm.invoke.return_value = mock_response
        mock_service._get_llm = lambda: mock_llm

        client.app.dependency_overrides[get_ai_service] = lambda: mock_service
        try:
            resp = client.post(
                "/api/v1/ai/analyze-failure",
                json={
                    "test_case_id": "tc-3",
                    "status": "failed",
                    "response": {"status_code": 500, "body": {}},
                },
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["root_cause"] == "服务端异常"
            assert data["confidence"] == 0.9
        finally:
            client.app.dependency_overrides.pop(get_ai_service, None)

    def test_invalid_body_returns_422(self, client):
        """缺少必填字段 test_case_id 时返回 422。"""
        resp = client.post(
            "/api/v1/ai/analyze-failure",
            json={"status": "failed"},
        )
        assert resp.status_code == 422
