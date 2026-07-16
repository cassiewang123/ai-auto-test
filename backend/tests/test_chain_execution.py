"""串联执行 API 测试：验证多接口变量传递、失败策略、模板替换等."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

import app.models  # noqa: F401  注册模型元数据
from app.api.v1.test_plans import _render_template
from app.models.project import Project
from app.schemas.execution import (
    AssertionResult,
    ExecutionResult,
    ExtractedVariable,
    RequestDefinition,
    ResponseData,
)

BASE = "/api/v1/test-plans"
CASES = "/api/v1/test-cases"
PROJECT_ID = "chain-test-project"


@pytest.fixture(autouse=True)
def _seed_chain_test_project(db_session):
    db_session.add(Project(id=PROJECT_ID, name="Chain test project"))
    db_session.commit()


def _create_plan(client, **overrides):
    """创建测试计划."""
    payload = {
        "name": "串联计划",
        "execution_mode": "sequential",
        "project_id": PROJECT_ID,
    }
    payload.update(overrides)
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _create_case(client, **overrides):
    """创建测试用例."""
    payload = {
        "title": "用例",
        "method": "GET",
        "url": "/x",
        "project_id": PROJECT_ID,
    }
    payload.update(overrides)
    resp = client.post(CASES, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _add_item(client, plan_id, case_id, order=0):
    """添加用例到计划."""
    resp = client.post(
        f"{BASE}/{plan_id}/items",
        json={"test_case_id": case_id, "order": order},
    )
    assert resp.status_code == 200, resp.text


def _make_result(
    test_case_id: str = "",
    status: str = "passed",
    extracted: dict | None = None,
    request_def: RequestDefinition | None = None,
) -> ExecutionResult:
    """构造 ExecutionResult 用于 mock."""
    extracted_vars = [
        ExtractedVariable(name=k, value=v, source="body")
        for k, v in (extracted or {}).items()
    ]
    return ExecutionResult(
        test_case_id=test_case_id,
        status=status,
        duration=0.01,
        request=request_def,
        response=ResponseData(
            status_code=200,
            headers={},
            body={"ok": True},
            elapsed=0.01,
            text='{"ok": true}',
        ),
        assertion_results=[
            AssertionResult(
                assertion_type="status_code",
                operator="eq",
                expected="200",
                actual=200,
                passed=True,
            )
        ],
        extracted_variables=extracted_vars,
        executed_at=datetime.now(),
    )


# ---------------------------------------------------------------------------
# 模板渲染函数测试
# ---------------------------------------------------------------------------
class TestRenderTemplate:
    def test_render_template(self):
        """${var} 替换函数正确替换字符串、字典、列表."""
        context = {"token": "abc123", "user_id": 42}

        # 字符串替换
        assert _render_template("Bearer ${token}", context) == "Bearer abc123"
        assert _render_template("/users/${user_id}", context) == "/users/42"

        # 字典替换（递归）
        result = _render_template(
            {"Authorization": "Bearer ${token}", "X-User-Id": "${user_id}"},
            context,
        )
        assert result == {
            "Authorization": "Bearer abc123",
            "X-User-Id": "42",
        }

        # 列表替换（递归）
        result = _render_template(
            ["${token}", "${user_id}", "plain"],
            context,
        )
        assert result == ["abc123", "42", "plain"]

        # 嵌套结构（字典 + 列表）
        result = _render_template(
            {"headers": {"Authorization": "${token}"}, "ids": [1, "${user_id}"]},
            context,
        )
        assert result == {
            "headers": {"Authorization": "abc123"},
            "ids": [1, "42"],
        }

    def test_render_template_unknown_var(self):
        """未命中的变量保持原样."""
        assert _render_template("hello ${missing}", {"a": 1}) == "hello ${missing}"

    def test_render_template_non_string(self):
        """非字符串/字典/列表原样返回."""
        assert _render_template(42, {"a": 1}) == 42
        assert _render_template(None, {"a": 1}) is None
        assert _render_template(True, {"a": 1}) is True


# ---------------------------------------------------------------------------
# 串联执行 API 测试
# ---------------------------------------------------------------------------
class TestChainExecution:
    def test_chain_variable_passing(self, client):
        """串联模式下变量能从前一个用例传递到后一个用例."""
        plan = _create_plan(
            client, scenario_type="chain", fail_strategy="continue"
        )
        # 用例1：登录，提取 token
        login_case = _create_case(
            client,
            title="登录",
            method="POST",
            url="/api/login",
            extract_rules=[
                {"name": "token", "source": "body", "expression": "$.token"}
            ],
        )
        # 用例2：获取用户信息，使用 ${token}
        profile_case = _create_case(
            client,
            title="获取用户信息",
            method="GET",
            url="/api/profile",
            headers={"Authorization": "Bearer ${token}"},
        )
        _add_item(client, plan["id"], login_case["id"], order=1)
        _add_item(client, plan["id"], profile_case["id"], order=2)

        # 用闭包记录每次调用时传入的请求定义，验证变量是否被正确渲染
        call_requests = []

        def fake_execute(request_def, assertions=None, variables=None, test_case_id=""):
            call_requests.append(request_def)
            if test_case_id == login_case["id"]:
                return _make_result(
                    test_case_id=test_case_id,
                    status="passed",
                    extracted={"token": "secret-token-xyz"},
                    request_def=request_def,
                )
            return _make_result(
                test_case_id=test_case_id,
                status="passed",
                request_def=request_def,
            )

        with patch("app.api.v1.test_plans._chain_executor") as mock_executor:
            mock_executor.execute.side_effect = fake_execute
            resp = client.post(f"{BASE}/{plan['id']}/execute-chain")

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] == 2
        assert data["passed"] == 2
        assert data["failed"] == 0

        # 最终响应脱敏，但内部上下文仍使用明文完成后续变量传递
        assert data["context_snapshot"]["token"] == "****"

        # 验证第二个用例的请求头被正确渲染（${token} 替换为实际值）
        assert len(call_requests) == 2
        second_request = call_requests[1]
        assert second_request.headers["Authorization"] == "Bearer secret-token-xyz"

    def test_chain_stop_on_failure(self, client):
        """fail_strategy='stop' 时遇失败中断."""
        plan = _create_plan(client, scenario_type="chain", fail_strategy="stop")
        case1 = _create_case(client, title="用例1", method="GET", url="/a")
        case2 = _create_case(client, title="用例2", method="GET", url="/b")
        case3 = _create_case(client, title="用例3", method="GET", url="/c")
        _add_item(client, plan["id"], case1["id"], order=1)
        _add_item(client, plan["id"], case2["id"], order=2)
        _add_item(client, plan["id"], case3["id"], order=3)

        def fake_execute(request_def, assertions=None, variables=None, test_case_id=""):
            if test_case_id == case2["id"]:
                return _make_result(
                    test_case_id=test_case_id,
                    status="failed",
                    request_def=request_def,
                )
            return _make_result(
                test_case_id=test_case_id,
                status="passed",
                request_def=request_def,
            )

        with patch("app.api.v1.test_plans._chain_executor") as mock_executor:
            mock_executor.execute.side_effect = fake_execute
            resp = client.post(f"{BASE}/{plan['id']}/execute-chain")

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        # 只执行了前2个用例（第2个失败后中断）
        assert data["total"] == 2
        assert data["passed"] == 1
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "passed"
        assert data["results"][1]["status"] == "failed"
        # 第3个用例未执行
        assert len(data["results"]) == 2

    def test_chain_continue_on_failure(self, client):
        """fail_strategy='continue' 时遇失败继续."""
        plan = _create_plan(
            client, scenario_type="chain", fail_strategy="continue"
        )
        case1 = _create_case(client, title="用例1", method="GET", url="/a")
        case2 = _create_case(client, title="用例2", method="GET", url="/b")
        case3 = _create_case(client, title="用例3", method="GET", url="/c")
        _add_item(client, plan["id"], case1["id"], order=1)
        _add_item(client, plan["id"], case2["id"], order=2)
        _add_item(client, plan["id"], case3["id"], order=3)

        def fake_execute(request_def, assertions=None, variables=None, test_case_id=""):
            if test_case_id == case2["id"]:
                return _make_result(
                    test_case_id=test_case_id,
                    status="failed",
                    request_def=request_def,
                )
            return _make_result(
                test_case_id=test_case_id,
                status="passed",
                request_def=request_def,
            )

        with patch("app.api.v1.test_plans._chain_executor") as mock_executor:
            mock_executor.execute.side_effect = fake_execute
            resp = client.post(f"{BASE}/{plan['id']}/execute-chain")

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        # 3 个用例全部执行
        assert data["total"] == 3
        assert data["passed"] == 2
        assert data["failed"] == 1
        statuses = [r["status"] for r in data["results"]]
        assert statuses == ["passed", "failed", "passed"]

    def test_chain_context_snapshot(self, client):
        """返回结果包含 context_snapshot."""
        plan = _create_plan(
            client, scenario_type="chain", fail_strategy="continue"
        )
        case1 = _create_case(
            client,
            title="登录",
            method="POST",
            url="/api/login",
            extract_rules=[
                {"name": "token", "source": "body", "expression": "$.token"},
                {"name": "user_id", "source": "body", "expression": "$.user.id"},
            ],
        )
        _add_item(client, plan["id"], case1["id"], order=1)

        with patch("app.api.v1.test_plans._chain_executor") as mock_executor:
            mock_executor.execute.return_value = _make_result(
                test_case_id=case1["id"],
                status="passed",
                extracted={"token": "tok-abc", "user_id": 1001},
            )
            resp = client.post(f"{BASE}/{plan['id']}/execute-chain")

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        # 必须包含 context_snapshot 字段
        assert "context_snapshot" in data
        assert isinstance(data["context_snapshot"], dict)
        assert data["context_snapshot"]["token"] == "****"
        assert data["context_snapshot"]["user_id"] == 1001
