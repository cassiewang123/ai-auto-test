"""执行编排器端到端测试：组合 请求构建→变量提取→断言→组装结果 的完整流程。

使用 httpx.MockTransport 构造真实 RequestBuilder，验证端到端行为，
覆盖 passed / failed / error 三类状态、变量跨用例传递、异常捕获等场景。
"""
from __future__ import annotations

import httpx
import pytest

from app.schemas.execution import (
    ExecutionResult,
    ExtractedVariable,
    RequestDefinition,
)
from test_engine.executor import TestCaseExecutor
from test_engine.request_builder import RequestBuilder


def make_executor(handler) -> TestCaseExecutor:
    builder = RequestBuilder(transport=httpx.MockTransport(handler))
    return TestCaseExecutor(request_builder=builder)


# ----------------------------- 正常流程 -----------------------------
class TestHappyPath:
    def test_execute_full_pass(self):
        def handler(request):
            return httpx.Response(200, json={"data": {"token": "tkn"}, "code": 0})

        executor = make_executor(handler)
        req = RequestDefinition(
            method="GET",
            url="https://api.test/login",
            extract_rules=[
                {"name": "token", "source": "json_path", "expression": "$.data.token"}
            ],
        )
        assertions = [
            {"assertion_type": "status_code", "operator": "eq", "expected": 200},
            {
                "assertion_type": "json_path",
                "expression": "$.data.token",
                "operator": "eq",
                "expected": "tkn",
            },
        ]
        result = executor.execute(req, assertions, test_case_id="tc-1")

        assert isinstance(result, ExecutionResult)
        assert result.test_case_id == "tc-1"
        assert result.status == "passed"
        assert result.response is not None
        assert result.response.status_code == 200
        assert result.response.body["data"]["token"] == "tkn"
        assert len(result.assertion_results) == 2
        assert all(r.passed for r in result.assertion_results)
        assert result.error_message is None
        assert result.error_traceback is None
        assert result.duration >= 0
        # 提取的变量
        assert len(result.extracted_variables) == 1
        assert result.extracted_variables[0].name == "token"
        assert result.extracted_variables[0].value == "tkn"

    def test_request_stored_in_result(self):
        def handler(request):
            return httpx.Response(200, json={"ok": True})

        executor = make_executor(handler)
        req = RequestDefinition(method="POST", url="https://api.test/x", body={"a": 1})
        result = executor.execute(req, [], test_case_id="tc")
        assert result.request is not None
        assert result.request.method == "POST"
        assert result.request.url == "https://api.test/x"

    def test_no_assertions_is_passed(self):
        def handler(request):
            return httpx.Response(200, json={"ok": True})

        executor = make_executor(handler)
        result = executor.execute(RequestDefinition(method="GET", url="https://api.test/"), [])
        assert result.status == "passed"
        assert result.assertion_results == []

    def test_response_time_assertion_end_to_end(self):
        def handler(request):
            return httpx.Response(200, json={"ok": True})

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/"),
            [{"assertion_type": "response_time", "operator": "le", "expected": 5.0}],
        )
        assert result.status == "passed"


# ----------------------------- 失败流程 -----------------------------
class TestFailedPath:
    def test_assertion_failed_status(self):
        def handler(request):
            return httpx.Response(200, json={"ok": True})

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/"),
            [{"assertion_type": "status_code", "operator": "eq", "expected": 404}],
        )
        assert result.status == "failed"
        assert result.response is not None
        assert result.assertion_results[0].passed is False
        assert result.error_message is None

    def test_mixed_assertions_failed(self):
        def handler(request):
            return httpx.Response(200, json={"count": 5})

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/"),
            [
                {"assertion_type": "status_code", "operator": "eq", "expected": 200},
                {"assertion_type": "json_path", "expression": "$.count", "operator": "eq", "expected": 10},
            ],
        )
        assert result.status == "failed"
        assert result.assertion_results[0].passed is True
        assert result.assertion_results[1].passed is False


# ----------------------------- 错误流程 -----------------------------
class TestErrorPath:
    def test_connection_error_captured(self):
        def handler(request):
            raise httpx.ConnectError("no connection", request=request)

        executor = make_executor(handler)
        result = executor.execute(RequestDefinition(method="GET", url="https://api.test/"), [])
        assert result.status == "error"
        assert result.response is None
        assert result.error_message is not None
        assert "ConnectError" in result.error_message
        assert result.error_traceback is not None
        assert "Traceback" in result.error_traceback
        assert result.assertion_results == []

    def test_timeout_error_captured(self):
        def handler(request):
            raise httpx.ReadTimeout("timed out", request=request)

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/", timeout=0.001), []
        )
        assert result.status == "error"
        assert result.error_message is not None
        assert "timeout" in result.error_message.lower() or "Timeout" in result.error_message


# ----------------------------- 变量提取与跨用例传递 -----------------------------
class TestVariableExtractionFlow:
    def test_extracted_variables_returned(self):
        def handler(request):
            return httpx.Response(
                200,
                json={"token": "TKN", "user": {"id": 7}},
                headers={"X-Trace": "trace-1"},
            )

        executor = make_executor(handler)
        req = RequestDefinition(
            method="GET",
            url="https://api.test/",
            extract_rules=[
                {"name": "token", "source": "json_path", "expression": "$.token"},
                {"name": "uid", "source": "json_path", "expression": "$.user.id"},
                {"name": "trace", "source": "header", "expression": "X-Trace"},
            ],
        )
        result = executor.execute(req, [])
        extracted = {ev.name: ev.value for ev in result.extracted_variables}
        assert extracted == {"token": "TKN", "uid": 7, "trace": "trace-1"}
        # 来源信息保留
        sources = {ev.name: ev.source for ev in result.extracted_variables}
        assert sources["trace"] == "header"

    def test_variable_chains_across_cases(self):
        state = {}

        def handler(request):
            path = request.url.path
            if path == "/auth":
                return httpx.Response(200, json={"token": "TKN123"})
            if path == "/profile":
                state["auth"] = request.headers.get("authorization")
                return httpx.Response(200, json={"name": "alice"})
            return httpx.Response(404)

        executor = make_executor(handler)
        r1 = executor.execute(
            RequestDefinition(
                method="GET",
                url="https://api.test/auth",
                extract_rules=[
                    {"name": "token", "source": "json_path", "expression": "$.token"}
                ],
            ),
            [],
            test_case_id="auth",
        )
        assert r1.status == "passed"
        pool = {ev.name: ev.value for ev in r1.extracted_variables}
        assert pool == {"token": "TKN123"}

        r2 = executor.execute(
            RequestDefinition(
                method="GET",
                url="https://api.test/profile",
                headers={"Authorization": "Bearer {{token}}"},
            ),
            [
                {
                    "assertion_type": "json_path",
                    "expression": "$.name",
                    "operator": "eq",
                    "expected": "alice",
                }
            ],
            variables=pool,
            test_case_id="profile",
        )
        assert r2.status == "passed"
        assert state["auth"] == "Bearer TKN123"

    def test_extraction_error_does_not_break_execution(self):
        def handler(request):
            return httpx.Response(200, json={"ok": True})

        executor = make_executor(handler)
        # 非法 JSONPath 表达式，提取器应安全降级为 None，不影响断言与状态
        result = executor.execute(
            RequestDefinition(
                method="GET",
                url="https://api.test/",
                extract_rules=[
                    {"name": "bad", "source": "json_path", "expression": "$.[invalid"}
                ],
            ),
            [{"assertion_type": "status_code", "operator": "eq", "expected": 200}],
        )
        assert result.status == "passed"
        assert result.extracted_variables[0].name == "bad"
        assert result.extracted_variables[0].value is None

    def test_variables_not_mutated_for_caller(self):
        def handler(request):
            return httpx.Response(
                200,
                json={"t": "v1"},
                extract_rules=[],
            )

        executor = make_executor(handler)
        original = {"existing": "1"}
        req = RequestDefinition(
            method="GET",
            url="https://api.test/",
            extract_rules=[{"name": "t", "source": "json_path", "expression": "$.t"}],
        )
        executor.execute(req, [], variables=original)
        # 调用方传入的 variables 字典不应被修改
        assert original == {"existing": "1"}


# --------------------------- 业务状态兜底 ---------------------------
class TestAutoBusinessStatus:
    """HTTP 200 但响应体报错时，不应被判为通过."""

    BUSINESS_FAILURE_BODY = {
        "flag": "f",
        "errorCode": 100,
        "errorInfo": "id not found",
        "code": 100,
        "message": "id not found",
        "data": None,
    }

    def test_http_200_with_business_error_fails(self):
        """只断言状态码时，业务失败应让整体结果为 failed."""
        def handler(request):
            return httpx.Response(200, json=self.BUSINESS_FAILURE_BODY)

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/public/updateInfo"),
            [{"assertion_type": "status_code", "operator": "eq", "expected": 200}],
        )

        assert result.status == "failed"
        # 状态码断言本身通过，追加的业务状态断言失败
        assert result.assertion_results[0].passed is True
        auto = result.assertion_results[-1]
        assert auto.assertion_type == "business_status"
        assert auto.passed is False
        assert auto.actual == "failed"

    def test_no_assertions_still_detects_business_error(self):
        """完全没有断言时，也应识别出业务失败."""
        def handler(request):
            return httpx.Response(200, json=self.BUSINESS_FAILURE_BODY)

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/x"), []
        )
        assert result.status == "failed"
        assert any(
            r.assertion_type == "business_status" and not r.passed
            for r in result.assertion_results
        )

    def test_business_success_keeps_passed_and_adds_nothing(self):
        """业务正常时不追加断言，保持结果与统计干净."""
        def handler(request):
            return httpx.Response(200, json={"code": 0, "data": {"name": "x"}})

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/x"),
            [{"assertion_type": "status_code", "operator": "eq", "expected": 200}],
        )
        assert result.status == "passed"
        assert len(result.assertion_results) == 1

    def test_body_assertion_disables_auto_check(self):
        """用例已显式断言响应体时，不再自动追加，尊重作者判断."""
        def handler(request):
            return httpx.Response(200, json=self.BUSINESS_FAILURE_BODY)

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/x"),
            [
                {"assertion_type": "status_code", "operator": "eq", "expected": 200},
                {
                    "assertion_type": "json_path",
                    "expression": "$.flag",
                    "operator": "eq",
                    "expected": "f",
                },
            ],
        )
        assert result.status == "passed"
        assert all(r.assertion_type != "business_status" for r in result.assertion_results)

    def test_author_can_assert_business_failure_explicitly(self):
        """显式期望业务失败时（负向用例），业务失败应判通过."""
        def handler(request):
            return httpx.Response(200, json=self.BUSINESS_FAILURE_BODY)

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/x"),
            [
                {"assertion_type": "status_code", "operator": "eq", "expected": 200},
                {
                    "assertion_type": "business_status",
                    "operator": "eq",
                    "expected": "failed",
                },
            ],
        )
        assert result.status == "passed"
        assert all(r.passed for r in result.assertion_results)

    def test_non_json_body_keeps_old_behavior(self):
        def handler(request):
            return httpx.Response(200, text="ok")

        executor = make_executor(handler)
        result = executor.execute(
            RequestDefinition(method="GET", url="https://api.test/x"),
            [{"assertion_type": "status_code", "operator": "eq", "expected": 200}],
        )
        assert result.status == "passed"
        assert len(result.assertion_results) == 1


# ----------------------------- 组件可注入 -----------------------------
class TestDependencyInjection:
    def test_default_components_created(self):
        executor = TestCaseExecutor()
        assert executor.request_builder is not None
        assert executor.assertion_engine is not None
        assert executor.variable_extractor is not None

    def test_custom_components_used(self):
        class SpyBuilder:
            called = False

            def send(self, request_def, variables=None):
                type(self).called = True
                from app.schemas.execution import ResponseData

                return ResponseData(status_code=200, body={"ok": True}, text="{}")

        spy = SpyBuilder()
        executor = TestCaseExecutor(request_builder=spy)
        result = executor.execute(RequestDefinition(method="GET", url="https://api.test/"), [])
        assert SpyBuilder.called is True
        assert result.status == "passed"
