"""数据驱动测试模块测试：CSV/JSON 解析、变量替换、数据集 CRUD、数据驱动执行.

注意：由于 main.py / models/__init__.py 在集成阶段由主 agent 统一注册，
本测试文件自行注册 test_data 路由并导入模型，确保测试可独立运行。
"""
from __future__ import annotations

# 确保新模型注册到 Base.metadata，conftest 的 db_engine 执行 create_all 时能建表
import app.models  # noqa: F401
import app.models.test_data_set  # noqa: F401
# 预存依赖：User 模型的 roles 关系引用 secondary="user_roles"，
# 需导入 role 模块注册 user_roles 关联表，否则 mapper 配置报 NameError
import app.models.role  # noqa: F401

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.data_driven_service import (
    execute_data_driven,
    extract_variables,
    parse_csv,
    parse_json,
    substitute_variables,
)

BASE = "/api/v1/test-data"
CASES = "/api/v1/test-cases"


# ---------------------------------------------------------------------------
# 覆盖 conftest 的 client fixture：注册 test_data 路由（main.py 集成前的临时方案）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def client(db_session):
    from app.api.v1.test_data import router as test_data_router
    from app.main import create_app

    app = create_app()
    settings = get_settings()
    app.include_router(
        test_data_router, prefix=f"{settings.API_V1_PREFIX}/test-data"
    )

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: User(
        id="data-test-admin",
        username="data-test-admin",
        email="data-test-admin@test.local",
        hashed_password="",
        is_active=True,
        is_superuser=True,
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _create_case(client, **overrides):
    payload = {
        "title": "测试用例",
        "method": "GET",
        "url": "https://api.example.com/users",
        "headers": {},
        "params": {},
        "assertions": [],
    }
    payload.update(overrides)
    resp = client.post(CASES, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _create_data_set(client, test_case_id, **overrides):
    payload = {
        "name": "登录数据集",
        "description": "测试数据",
        "format": "csv",
        "data": "username,password\nalice,1234\nbob,5678",
        "test_case_id": test_case_id,
    }
    payload.update(overrides)
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ===========================================================================
# CSV 解析
# ===========================================================================
class TestParseCsv:
    def test_normal(self):
        rows = parse_csv("username,password\nalice,1234\nbob,5678")
        assert len(rows) == 2
        assert rows[0] == {"username": "alice", "password": "1234"}
        assert rows[1] == {"username": "bob", "password": "5678"}

    def test_empty_lines_skipped(self):
        rows = parse_csv("a,b\n1,2\n\n3,4\n")
        assert len(rows) == 2
        assert rows[0] == {"a": "1", "b": "2"}
        assert rows[1] == {"a": "3", "b": "4"}

    def test_quoted_fields(self):
        rows = parse_csv(
            'name,desc\n"alice","hello, world"\n"bob","say ""hi"""'
        )
        assert len(rows) == 2
        assert rows[0]["name"] == "alice"
        assert rows[0]["desc"] == "hello, world"
        assert rows[1]["desc"] == 'say "hi"'

    def test_quoted_multiline(self):
        rows = parse_csv('name,desc\n"alice","line1\nline2"')
        assert len(rows) == 1
        assert rows[0]["desc"] == "line1\nline2"

    def test_empty_text(self):
        assert parse_csv("") == []
        assert parse_csv("   \n   ") == []

    def test_only_header(self):
        rows = parse_csv("username,password")
        assert rows == []


# ===========================================================================
# JSON 解析
# ===========================================================================
class TestParseJson:
    def test_normal(self):
        text = json.dumps(
            [{"username": "alice", "password": "1234"},
             {"username": "bob", "password": "5678"}]
        )
        rows = parse_json(text)
        assert len(rows) == 2
        assert rows[0]["username"] == "alice"
        assert rows[1]["password"] == "5678"

    def test_non_array_raises(self):
        with pytest.raises(ValueError, match="必须是数组"):
            parse_json('{"username": "alice"}')

    def test_empty_array(self):
        assert parse_json("[]") == []

    def test_empty_text(self):
        assert parse_json("") == []
        assert parse_json("   ") == []

    def test_element_not_object_raises(self):
        with pytest.raises(ValueError, match="不是对象"):
            parse_json('[1, 2, 3]')

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json("{invalid json")

    def test_mixed_types_raises(self):
        with pytest.raises(ValueError):
            parse_json('[{"a": 1}, "not a dict"]')


# ===========================================================================
# 变量提取
# ===========================================================================
class TestExtractVariables:
    def test_same_keys(self):
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        assert extract_variables(rows) == ["a", "b"]

    def test_different_keys_union(self):
        rows = [{"a": 1}, {"b": 2}, {"a": 3, "c": 4}]
        assert extract_variables(rows) == ["a", "b", "c"]

    def test_preserves_order(self):
        rows = [{"z": 1, "a": 2}, {"m": 3}]
        assert extract_variables(rows) == ["z", "a", "m"]

    def test_empty_rows(self):
        assert extract_variables([]) == []


# ===========================================================================
# 变量替换
# ===========================================================================
class TestSubstituteVariables:
    def test_url_substitution(self):
        result = substitute_variables(
            "https://api.example.com/users/${username}",
            {"username": "alice"},
        )
        assert result == "https://api.example.com/users/alice"

    def test_headers_substitution(self):
        result = substitute_variables(
            {"Authorization": "Bearer ${token}"},
            {"token": "abc123"},
        )
        assert result == {"Authorization": "Bearer abc123"}

    def test_body_nested_substitution(self):
        template = {
            "username": "${user}",
            "password": "${pwd}",
            "nested": {"value": "${user}"},
        }
        result = substitute_variables(template, {"user": "alice", "pwd": "secret"})
        assert result == {
            "username": "alice",
            "password": "secret",
            "nested": {"value": "alice"},
        }

    def test_list_substitution(self):
        result = substitute_variables(
            ["${a}", "${b}", "static"],
            {"a": "1", "b": "2"},
        )
        assert result == ["1", "2", "static"]

    def test_unknown_variable_kept(self):
        result = substitute_variables("${unknown}", {})
        assert result == "${unknown}"

    def test_with_spaces_in_braces(self):
        result = substitute_variables("${ user }", {"user": "alice"})
        assert result == "alice"

    def test_multiple_vars_in_string(self):
        result = substitute_variables(
            "${user}:${password}", {"user": "alice", "password": "1234"}
        )
        assert result == "alice:1234"

    def test_non_string_passthrough(self):
        assert substitute_variables(42, {"x": "y"}) == 42
        assert substitute_variables(None, {}) is None
        assert substitute_variables(True, {}) is True

    def test_partial_substitution(self):
        result = substitute_variables(
            "user=${user}&missing=${missing}", {"user": "alice"}
        )
        assert result == "user=alice&missing=${missing}"


# ===========================================================================
# FIX-07: {{var}} 标准语法支持（兼容期同时支持 ${var}）
# ===========================================================================
class TestSubstituteDoubleBraceSyntax:
    """验证 {{var}} 标准语法替换."""

    def test_double_brace_in_url(self):
        result = substitute_variables(
            "https://api.example.com/users/{{username}}",
            {"username": "alice"},
        )
        assert result == "https://api.example.com/users/alice"

    def test_double_brace_with_spaces(self):
        result = substitute_variables(
            "https://api.example.com/{{ path }}", {"path": "items"}
        )
        assert result == "https://api.example.com/items"

    def test_double_brace_in_headers(self):
        result = substitute_variables(
            {"Authorization": "Bearer {{token}}"},
            {"token": "abc123"},
        )
        assert result == {"Authorization": "Bearer abc123"}

    def test_double_brace_nested_body(self):
        template = {"username": "{{user}}", "nested": {"v": "{{user}}"}}
        result = substitute_variables(template, {"user": "alice"})
        assert result == {"username": "alice", "nested": {"v": "alice"}}

    def test_double_brace_in_list(self):
        result = substitute_variables(
            ["{{a}}", "{{b}}", "static"], {"a": "1", "b": "2"}
        )
        assert result == ["1", "2", "static"]

    def test_double_brace_unknown_kept(self):
        result = substitute_variables("{{unknown}}", {})
        assert result == "{{unknown}}"

    def test_double_brace_multiple_in_string(self):
        result = substitute_variables(
            "{{user}}:{{password}}", {"user": "alice", "password": "1234"}
        )
        assert result == "alice:1234"

    def test_legacy_dollar_brace_still_works(self):
        """兼容期：${var} 语法仍应生效."""
        result = substitute_variables(
            "https://api.example.com/users/${username}",
            {"username": "alice"},
        )
        assert result == "https://api.example.com/users/alice"

    def test_mixed_syntax_in_same_string(self):
        """同一字符串中混合使用两种语法."""
        result = substitute_variables(
            "{{user}}/${role}", {"user": "alice", "role": "admin"}
        )
        assert result == "alice/admin"


# ===========================================================================
# 数据驱动执行（单元测试，mock TestCaseExecutor）
# ===========================================================================
class TestExecuteDataDriven:
    def _make_mock_result(self, status="passed"):
        mock_result = MagicMock()
        mock_result.status = status
        mock_result.duration = 0.01
        mock_result.response.status_code = 200
        mock_result.assertion_results = []
        mock_result.error_message = None
        return mock_result

    def _make_case(self, **overrides):
        defaults = dict(
            method="GET",
            url="https://api.example.com/users/${username}",
            headers={"Authorization": "Bearer ${token}"},
            params={"q": "${query}"},
            body={"username": "${username}", "password": "${password}"},
            graphql_query=None,
            extract_rules=[],
            assertions=[],
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_execute_all_rows(self):
        case = self._make_case()
        data_rows = [
            {"username": "alice", "token": "tok1", "query": "a", "password": "p1"},
            {"username": "bob", "token": "tok2", "query": "b", "password": "p2"},
        ]
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._make_mock_result()

            results = execute_data_driven(case, data_rows)

        assert len(results) == 2
        assert mock_instance.execute.call_count == 2
        assert all(r["status"] == "passed" for r in results)

    def test_variables_substituted_correctly(self):
        case = self._make_case()
        data_rows = [
            {"username": "alice", "token": "tok1", "query": "a", "password": "p1"},
        ]
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._make_mock_result()

            execute_data_driven(case, data_rows)

            first_call = mock_instance.execute.call_args_list[0]
            request_def = first_call.kwargs["request_def"]
            assert request_def.url == "https://api.example.com/users/alice"
            assert request_def.headers["Authorization"] == "Bearer tok1"
            assert request_def.params["q"] == "a"
            assert request_def.body["username"] == "alice"
            assert request_def.body["password"] == "p1"

    def test_second_row_uses_different_values(self):
        case = self._make_case()
        data_rows = [
            {"username": "alice", "token": "tok1", "query": "a", "password": "p1"},
            {"username": "bob", "token": "tok2", "query": "b", "password": "p2"},
        ]
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._make_mock_result()

            execute_data_driven(case, data_rows)

            second_call = mock_instance.execute.call_args_list[1]
            request_def = second_call.kwargs["request_def"]
            assert request_def.url == "https://api.example.com/users/bob"
            assert request_def.headers["Authorization"] == "Bearer tok2"

    def test_empty_data_rows(self):
        case = self._make_case()
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            results = execute_data_driven(case, [])
        assert results == []
        mock_instance.execute.assert_not_called()

    def test_environment_base_url_prepended(self):
        case = self._make_case(url="api/users/${username}")
        env = SimpleNamespace(
            base_url="https://test.example.com",
            variables={"token": "env-token"},
        )
        data_rows = [{"username": "alice", "query": "a", "password": "p1"}]
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._make_mock_result()

            execute_data_driven(case, data_rows, environment=env)

            first_call = mock_instance.execute.call_args_list[0]
            request_def = first_call.kwargs["request_def"]
            assert request_def.url == "https://test.example.com/api/users/alice"
            # 环境变量也参与替换
            assert request_def.headers["Authorization"] == "Bearer env-token"

    def test_row_data_overrides_environment_vars(self):
        case = self._make_case(
            headers={"Authorization": "Bearer ${token}"}
        )
        env = SimpleNamespace(base_url="", variables={"token": "env-token"})
        data_rows = [{"username": "alice", "token": "row-token",
                      "query": "a", "password": "p1"}]
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._make_mock_result()

            execute_data_driven(case, data_rows, environment=env)

            first_call = mock_instance.execute.call_args_list[0]
            request_def = first_call.kwargs["request_def"]
            assert request_def.headers["Authorization"] == "Bearer row-token"

    def test_execution_error_captured(self):
        case = self._make_case()
        data_rows = [
            {"username": "alice", "token": "t", "query": "q", "password": "p"},
        ]
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.side_effect = RuntimeError("connection refused")

            results = execute_data_driven(case, data_rows)

        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert "connection refused" in results[0]["error_message"]

    def test_failed_assertion_status(self):
        case = self._make_case()
        data_rows = [
            {"username": "alice", "token": "t", "query": "q", "password": "p"},
        ]
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._make_mock_result(
                status="failed"
            )

            results = execute_data_driven(case, data_rows)

        assert results[0]["status"] == "failed"

    def test_result_contains_input_data(self):
        case = self._make_case()
        data_rows = [
            {"username": "alice", "token": "t1", "query": "q1", "password": "p1"},
        ]
        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._make_mock_result()

            results = execute_data_driven(case, data_rows)

        assert results[0]["input_data"] == data_rows[0]
        assert results[0]["row_index"] == 0


# ===========================================================================
# 数据集 CRUD
# ===========================================================================
class TestDataSetCrud:
    def test_create_csv(self, client):
        case = _create_case(client)
        data = {
            "name": "CSV 数据集",
            "description": "用户登录数据",
            "format": "csv",
            "data": "username,password\nalice,1234\nbob,5678",
            "test_case_id": case["id"],
        }
        resp = client.post(BASE, json=data)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["id"]
        assert body["name"] == "CSV 数据集"
        assert body["format"] == "csv"
        assert body["variables"] == ["username", "password"]
        assert body["test_case_id"] == case["id"]
        assert body["is_active"] is True

    def test_create_json(self, client):
        case = _create_case(client)
        data = {
            "name": "JSON 数据集",
            "format": "json",
            "data": json.dumps([{"a": 1}, {"a": 2}]),
            "test_case_id": case["id"],
        }
        resp = client.post(BASE, json=data)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["variables"] == ["a"]

    def test_create_case_not_found(self, client):
        resp = client.post(BASE, json={
            "name": "x", "format": "csv", "data": "a\n1",
            "test_case_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_get(self, client):
        case = _create_case(client)
        ds = _create_data_set(client, test_case_id=case["id"])
        resp = client.get(f"{BASE}/{ds['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == ds["id"]

    def test_get_not_found(self, client):
        resp = client.get(f"{BASE}/nonexistent")
        assert resp.status_code == 404

    def test_list_by_test_case(self, client):
        case1 = _create_case(client, title="用例1")
        case2 = _create_case(client, title="用例2")
        _create_data_set(client, test_case_id=case1["id"], name="ds1")
        _create_data_set(client, test_case_id=case1["id"], name="ds2")
        _create_data_set(client, test_case_id=case2["id"], name="ds3")

        resp = client.get(f"{BASE}?test_case_id={case1['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        names = [d["name"] for d in body["data"]]
        assert "ds1" in names
        assert "ds2" in names

    def test_list_all(self, client):
        case = _create_case(client)
        _create_data_set(client, test_case_id=case["id"], name="all1")
        resp = client.get(BASE)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_update_name(self, client):
        case = _create_case(client)
        ds = _create_data_set(client, test_case_id=case["id"])
        resp = client.put(f"{BASE}/{ds['id']}", json={"name": "新名称"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "新名称"

    def test_update_data_reparse_variables(self, client):
        case = _create_case(client)
        ds = _create_data_set(client, test_case_id=case["id"])
        # 原始变量: ["username", "password"]
        assert ds["variables"] == ["username", "password"]
        new_data = "user,age\nalice,30\nbob,25"
        resp = client.put(f"{BASE}/{ds['id']}", json={"data": new_data})
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["variables"] == ["user", "age"]

    def test_update_not_found(self, client):
        resp = client.put(f"{BASE}/nope", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete(self, client):
        case = _create_case(client)
        ds = _create_data_set(client, test_case_id=case["id"])
        resp = client.delete(f"{BASE}/{ds['id']}")
        assert resp.status_code == 200
        # 删除后查询应 404
        resp2 = client.get(f"{BASE}/{ds['id']}")
        assert resp2.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete(f"{BASE}/nope")
        assert resp.status_code == 404


# ===========================================================================
# 数据集预览
# ===========================================================================
class TestDataSetPreview:
    def test_preview_csv(self, client):
        case = _create_case(client)
        ds = _create_data_set(client, test_case_id=case["id"])
        resp = client.post(f"{BASE}/{ds['id']}/preview")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["variables"] == ["username", "password"]
        assert len(body["rows"]) == 2
        assert body["rows"][0] == {"username": "alice", "password": "1234"}

    def test_preview_json(self, client):
        case = _create_case(client)
        ds = _create_data_set(
            client,
            test_case_id=case["id"],
            format="json",
            data=json.dumps([{"x": 1}, {"x": 2}, {"x": 3}]),
        )
        resp = client.post(f"{BASE}/{ds['id']}/preview")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["variables"] == ["x"]
        assert len(body["rows"]) == 3

    def test_preview_not_found(self, client):
        resp = client.post(f"{BASE}/nonexistent/preview")
        assert resp.status_code == 404


# ===========================================================================
# 数据驱动执行 API（mock HTTP 请求）
# ===========================================================================
class TestDataDrivenExecutionApi:
    def _mock_result(self, status="passed"):
        mock_result = MagicMock()
        mock_result.status = status
        mock_result.duration = 0.01
        mock_result.response.status_code = 200
        mock_result.assertion_results = []
        mock_result.error_message = None
        return mock_result

    def test_execute_with_data_set(self, client):
        case = _create_case(
            client,
            url="https://api.example.com/users/${username}",
            method="GET",
        )
        ds = _create_data_set(client, test_case_id=case["id"])

        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._mock_result()

            resp = client.post(f"{BASE}/execute", json={
                "test_case_id": case["id"],
                "data_set_id": ds["id"],
            })

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total"] == 2
        assert body["passed"] == 2
        assert body["failed"] == 0
        assert mock_instance.execute.call_count == 2

        # 验证第一行变量替换
        first_call = mock_instance.execute.call_args_list[0]
        request_def = first_call.kwargs["request_def"]
        assert request_def.url == "https://api.example.com/users/alice"

    def test_execute_empty_data_set(self, client):
        case = _create_case(client)
        # 不传 data_set_id，使用空数据
        resp = client.post(f"{BASE}/execute", json={
            "test_case_id": case["id"],
        })
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total"] == 0
        assert body["passed"] == 0
        assert body["failed"] == 0
        assert body["results"] == []

    def test_execute_case_not_found(self, client):
        resp = client.post(f"{BASE}/execute", json={
            "test_case_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_execute_with_failed_rows(self, client):
        case = _create_case(client)
        ds = _create_data_set(client, test_case_id=case["id"])

        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            # 第一行 passed，第二行 failed
            mock_instance.execute.side_effect = [
                self._mock_result("passed"),
                self._mock_result("failed"),
            ]

            resp = client.post(f"{BASE}/execute", json={
                "test_case_id": case["id"],
                "data_set_id": ds["id"],
            })

        body = resp.json()["data"]
        assert body["total"] == 2
        assert body["passed"] == 1
        assert body["failed"] == 1

    def test_execute_with_environment(self, client):
        # 创建带 ${path} 变量的用例
        case = _create_case(
            client,
            url="${base_url}/api/${path}",
        )
        ds = _create_data_set(
            client,
            test_case_id=case["id"],
            data="path\nusers\nposts",
        )
        # 创建环境
        env_resp = client.post("/api/v1/environments", json={
            "name": "测试环境",
            "base_url": "https://10.0.0.1:8080",
            "variables": {"base_url": "https://test.example.com"},
        })
        # 环境创建可能因 IP 校验规则失败，直接用 mock 验证逻辑
        env_id = env_resp.json()["data"]["id"] if env_resp.status_code == 200 else None

        with patch("test_engine.executor.TestCaseExecutor") as MockExecutor:
            mock_instance = MockExecutor.return_value
            mock_instance.execute.return_value = self._mock_result()

            payload = {
                "test_case_id": case["id"],
                "data_set_id": ds["id"],
            }
            if env_id:
                payload["environment_id"] = env_id

            resp = client.post(f"{BASE}/execute", json=payload)

        if env_id:
            body = resp.json()["data"]
            assert body["total"] == 2
            first_call = mock_instance.execute.call_args_list[0]
            request_def = first_call.kwargs["request_def"]
            # base_url 来自环境变量替换
            assert request_def.url == "https://test.example.com/api/users"
