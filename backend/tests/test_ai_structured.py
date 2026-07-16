"""AI 结构化用例生成测试。

测试通过 API 端点验证结构化用例生成与导入功能。
由于无 LLM 配置，所有测试走 fallback 路径。
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# POST /api/v1/ai/generate-test-cases
# ---------------------------------------------------------------------------
class TestGenerateStructuredCases:
    def test_generate_structured_cases_description(self, client):
        """从描述生成结构化用例。"""
        resp = client.post(
            "/api/v1/ai/generate-test-cases",
            json={
                "source_type": "description",
                "source_data": {"description": "测试用户登录功能"},
                "options": {},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        cases = body["data"]["cases"]
        assert isinstance(cases, list)
        assert len(cases) > 0

    def test_generate_structured_cases_interface(self, client):
        """从接口信息生成结构化用例。"""
        resp = client.post(
            "/api/v1/ai/generate-test-cases",
            json={
                "source_type": "interface",
                "source_data": {
                    "method": "POST",
                    "url": "/api/v1/users",
                    "body": {"username": "test", "email": "test@example.com"},
                },
                "options": {},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        cases = body["data"]["cases"]
        assert isinstance(cases, list)
        assert len(cases) > 0

    def test_generate_cases_returns_structure(self, client):
        """返回结构包含 title/method/url/headers/body/assertions。"""
        resp = client.post(
            "/api/v1/ai/generate-test-cases",
            json={
                "source_type": "description",
                "source_data": {"description": "测试用户注册"},
                "options": {},
            },
        )
        assert resp.status_code == 200
        cases = resp.json()["data"]["cases"]
        for case in cases:
            assert "title" in case
            assert "method" in case
            assert "url" in case
            assert "headers" in case
            assert "body" in case
            assert "assertions" in case
            assert isinstance(case["assertions"], list)

    def test_generate_cases_types(self, client):
        """生成 normal/exception/boundary 三类用例。"""
        resp = client.post(
            "/api/v1/ai/generate-test-cases",
            json={
                "source_type": "interface",
                "source_data": {
                    "method": "GET",
                    "url": "/api/v1/users",
                },
                "options": {},
            },
        )
        assert resp.status_code == 200
        cases = resp.json()["data"]["cases"]
        case_types = {c.get("case_type") for c in cases}
        assert "normal" in case_types
        assert "exception" in case_types
        assert "boundary" in case_types


# ---------------------------------------------------------------------------
# POST /api/v1/ai/import-cases
# ---------------------------------------------------------------------------
class TestImportCases:
    def test_import_cases(self, client):
        """批量入库。"""
        resp = client.post(
            "/api/v1/ai/import-cases",
            json={
                "cases": [
                    {
                        "title": "测试用例1",
                        "case_type": "normal",
                        "priority": "P0",
                        "method": "POST",
                        "url": "/api/v1/users",
                        "headers": {"Content-Type": "application/json"},
                        "body": {"name": "test"},
                        "assertions": [
                            {"type": "status_code", "expected": "200"}
                        ],
                        "description": "测试描述",
                    },
                    {
                        "title": "测试用例2",
                        "case_type": "exception",
                        "priority": "P1",
                        "method": "POST",
                        "url": "/api/v1/users",
                        "headers": {"Content-Type": "application/json"},
                        "body": {},
                        "assertions": [
                            {"type": "status_code", "expected": "400"}
                        ],
                        "description": "异常测试",
                    },
                ],
                "project_id": None,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["created_count"] == 2
        assert len(body["data"]["case_ids"]) == 2

    def test_import_cases_with_assertions(self, client):
        """入库时级联创建断言规则。"""
        # 先导入
        resp = client.post(
            "/api/v1/ai/import-cases",
            json={
                "cases": [
                    {
                        "title": "带断言用例",
                        "case_type": "normal",
                        "priority": "P0",
                        "method": "GET",
                        "url": "/api/v1/users/1",
                        "headers": {},
                        "body": None,
                        "assertions": [
                            {"type": "status_code", "expected": "200"},
                            {
                                "type": "json_path",
                                "expression": "$.id",
                                "operator": "type",
                                "expected": "integer",
                            },
                        ],
                        "description": "验证断言级联",
                    },
                ],
                "project_id": None,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["created_count"] == 1
        case_id = body["data"]["case_ids"][0]

        # 验证断言规则已级联创建
        case_resp = client.get(f"/api/v1/test-cases/{case_id}")
        assert case_resp.status_code == 200
        case_data = case_resp.json()["data"]
        assert len(case_data["assertions"]) == 2
        assertion_types = [a["assertion_type"] for a in case_data["assertions"]]
        assert "status_code" in assertion_types
        assert "json_path" in assertion_types
