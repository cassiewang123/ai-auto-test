"""断言引擎单元测试：覆盖 status_code / json_path / header / response_time / json_schema，
含通过、失败、边界与错误场景。"""
from __future__ import annotations

import pytest

from app.schemas.execution import ResponseData
from test_engine.assertion_engine import AssertionEngine, inspect_business_status


@pytest.fixture
def engine():
    return AssertionEngine()


# ----------------------------- status_code -----------------------------
class TestStatusCodeAssertion:
    @pytest.mark.parametrize("code,op,expected,passed", [
        (200, "eq", 200, True),
        (200, "eq", 404, False),
        (200, "ne", 404, True),
        (200, "ne", 200, False),
        (404, "gt", 200, True),
        (200, "gt", 404, False),
        (100, "lt", 200, True),
        (200, "ge", 200, True),
        (200, "le", 200, True),
        (300, "le", 200, False),
    ])
    def test_status_code_operators(self, engine, code, op, expected, passed):
        resp = ResponseData(status_code=code)
        rule = {"assertion_type": "status_code", "operator": op, "expected": expected}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is passed
        assert result.actual == code

    def test_expected_from_json_encoded_string(self, engine):
        # ORM 以 JSON 文本存储 expected，引擎应能解析 "200" -> 200
        resp = ResponseData(status_code=200)
        rule = {"assertion_type": "status_code", "operator": "eq", "expected": "200"}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_failure_message_populated(self, engine):
        resp = ResponseData(status_code=404)
        rule = {"assertion_type": "status_code", "operator": "eq", "expected": 200}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is False
        assert result.message  # 非空失败原因


# ----------------------------- json_path -----------------------------
class TestJsonPathAssertion:
    def test_eq_pass(self, engine):
        resp = ResponseData(status_code=200, body={"data": {"count": 5}})
        rule = {"assertion_type": "json_path", "expression": "$.data.count", "operator": "eq", "expected": 5}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is True
        assert result.actual == 5

    def test_eq_fail(self, engine):
        resp = ResponseData(status_code=200, body={"data": {"count": 5}})
        rule = {"assertion_type": "json_path", "expression": "$.data.count", "operator": "eq", "expected": 10}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is False

    @pytest.mark.parametrize("count,op,expected,passed", [
        (5, "gt", 3, True),
        (5, "gt", 5, False),
        (5, "ge", 5, True),
        (5, "lt", 10, True),
        (5, "le", 5, True),
        (5, "ne", 3, True),
    ])
    def test_numeric_operators(self, engine, count, op, expected, passed):
        resp = ResponseData(status_code=200, body={"data": {"count": count}})
        rule = {"assertion_type": "json_path", "expression": "$.data.count", "operator": op, "expected": expected}
        assert engine.evaluate(resp, [rule])[0].passed is passed

    def test_contains_in_string(self, engine):
        resp = ResponseData(status_code=200, body={"data": {"name": "alice cooper"}})
        rule = {"assertion_type": "json_path", "expression": "$.data.name", "operator": "contains", "expected": "alice"}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_contains_in_list(self, engine):
        resp = ResponseData(status_code=200, body={"tags": ["smoke", "api"]})
        rule = {"assertion_type": "json_path", "expression": "$.tags", "operator": "contains", "expected": "api"}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_contains_fail(self, engine):
        resp = ResponseData(status_code=200, body={"tags": ["smoke"]})
        rule = {"assertion_type": "json_path", "expression": "$.tags", "operator": "contains", "expected": "api"}
        assert engine.evaluate(resp, [rule])[0].passed is False

    def test_regex_match(self, engine):
        resp = ResponseData(status_code=200, body={"data": {"email": "user@example.com"}})
        rule = {"assertion_type": "json_path", "expression": "$.data.email", "operator": "regex", "expected": r"^[\w.]+@example\.com$"}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_regex_no_match(self, engine):
        resp = ResponseData(status_code=200, body={"data": {"email": "user@other.com"}})
        rule = {"assertion_type": "json_path", "expression": "$.data.email", "operator": "regex", "expected": r"^[\w.]+@example\.com$"}
        assert engine.evaluate(resp, [rule])[0].passed is False

    def test_type_int(self, engine):
        resp = ResponseData(status_code=200, body={"data": {"count": 5}})
        rule = {"assertion_type": "json_path", "expression": "$.data.count", "operator": "type", "expected": "int"}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_type_str(self, engine):
        resp = ResponseData(status_code=200, body={"data": {"name": "alice"}})
        rule = {"assertion_type": "json_path", "expression": "$.data.name", "operator": "type", "expected": "str"}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_type_bool_not_int(self, engine):
        # bool 不应被误判为 int
        resp = ResponseData(status_code=200, body={"active": True})
        rule_int = {"assertion_type": "json_path", "expression": "$.active", "operator": "type", "expected": "int"}
        rule_bool = {"assertion_type": "json_path", "expression": "$.active", "operator": "type", "expected": "bool"}
        assert engine.evaluate(resp, [rule_int])[0].passed is False
        assert engine.evaluate(resp, [rule_bool])[0].passed is True

    def test_json_path_no_match_fails_with_none_actual(self, engine):
        resp = ResponseData(status_code=200, body={"data": {}})
        rule = {"assertion_type": "json_path", "expression": "$.data.missing", "operator": "eq", "expected": "x"}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is False
        assert result.actual is None


# ----------------------------- header -----------------------------
class TestHeaderAssertion:
    def test_header_eq_pass(self, engine):
        resp = ResponseData(status_code=200, headers={"Content-Type": "application/json"})
        rule = {"assertion_type": "header", "expression": "Content-Type", "operator": "eq", "expected": "application/json"}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_header_case_insensitive(self, engine):
        resp = ResponseData(status_code=200, headers={"content-type": "application/json"})
        rule = {"assertion_type": "header", "expression": "Content-Type", "operator": "eq", "expected": "application/json"}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_header_missing_fails(self, engine):
        resp = ResponseData(status_code=200, headers={})
        rule = {"assertion_type": "header", "expression": "Authorization", "operator": "eq", "expected": "Bearer x"}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is False
        assert result.actual is None

    def test_header_contains(self, engine):
        resp = ResponseData(status_code=200, headers={"Content-Type": "application/json; charset=utf-8"})
        rule = {"assertion_type": "header", "expression": "Content-Type", "operator": "contains", "expected": "json"}
        assert engine.evaluate(resp, [rule])[0].passed is True


# ----------------------------- response_time -----------------------------
class TestResponseTimeAssertion:
    def test_le_pass(self, engine):
        resp = ResponseData(status_code=200, elapsed=0.5)
        rule = {"assertion_type": "response_time", "operator": "le", "expected": 1.0}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_le_fail(self, engine):
        resp = ResponseData(status_code=200, elapsed=2.0)
        rule = {"assertion_type": "response_time", "operator": "le", "expected": 1.0}
        assert engine.evaluate(resp, [rule])[0].passed is False

    def test_gt_threshold(self, engine):
        resp = ResponseData(status_code=200, elapsed=2.0)
        rule = {"assertion_type": "response_time", "operator": "gt", "expected": 1.0}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_expected_threshold_from_string(self, engine):
        # ORM 存储 expected 为 JSON 文本 "1.0" -> 1.0
        resp = ResponseData(status_code=200, elapsed=0.5)
        rule = {"assertion_type": "response_time", "operator": "le", "expected": "1.0"}
        assert engine.evaluate(resp, [rule])[0].passed is True


# ----------------------------- json_schema -----------------------------
class TestJsonSchemaAssertion:
    def test_schema_valid_pass(self, engine):
        resp = ResponseData(status_code=200, body={"name": "alice", "age": 30})
        schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        rule = {"assertion_type": "json_schema", "expected": schema}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is True

    def test_schema_invalid_fails(self, engine):
        resp = ResponseData(status_code=200, body={"name": "alice"})  # 缺 age
        schema = {"type": "object", "required": ["name", "age"]}
        rule = {"assertion_type": "json_schema", "expected": schema}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is False
        assert result.message  # 含校验错误信息

    def test_schema_from_expression_json_string(self, engine):
        # schema 以 JSON 字符串形式放在 expression
        resp = ResponseData(status_code=200, body={"name": "alice"})
        rule = {"assertion_type": "json_schema", "expression": '{"type": "object", "required": ["name"]}'}
        assert engine.evaluate(resp, [rule])[0].passed is True

    def test_schema_on_non_dict_body_fails(self, engine):
        resp = ResponseData(status_code=200, body="not an object", text="not an object")
        schema = {"type": "object"}
        rule = {"assertion_type": "json_schema", "expected": schema}
        assert engine.evaluate(resp, [rule])[0].passed is False


# ----------------------------- 整体状态 / 边界 -----------------------------
class TestOverallAndEdgeCases:
    def test_all_passed(self, engine):
        resp = ResponseData(status_code=200, body={"count": 5}, elapsed=0.1)
        rules = [
            {"assertion_type": "status_code", "operator": "eq", "expected": 200},
            {"assertion_type": "json_path", "expression": "$.count", "operator": "eq", "expected": 5},
        ]
        results = engine.evaluate(resp, rules)
        assert engine.all_passed(results) is True

    def test_any_failed(self, engine):
        resp = ResponseData(status_code=200, body={"count": 5})
        rules = [
            {"assertion_type": "status_code", "operator": "eq", "expected": 200},
            {"assertion_type": "json_path", "expression": "$.count", "operator": "eq", "expected": 10},
        ]
        results = engine.evaluate(resp, rules)
        assert engine.all_passed(results) is False

    def test_empty_assertions_is_pass(self, engine):
        resp = ResponseData(status_code=200)
        results = engine.evaluate(resp, [])
        assert results == []
        assert engine.all_passed(results) is True

    def test_result_fields_populated(self, engine):
        resp = ResponseData(status_code=200, body={"count": 5})
        rule = {"assertion_type": "json_path", "expression": "$.count", "operator": "eq", "expected": 5}
        r = engine.evaluate(resp, [rule])[0]
        assert r.assertion_type == "json_path"
        assert r.expression == "$.count"
        assert r.operator == "eq"
        assert r.expected == 5
        assert r.actual == 5
        assert r.passed is True

    def test_unknown_assertion_type_fails_gracefully(self, engine):
        resp = ResponseData(status_code=200)
        rule = {"assertion_type": "magic", "operator": "eq", "expected": 1}
        r = engine.evaluate(resp, [rule])[0]
        assert r.passed is False
        assert "magic" in r.message or "不支持" in r.message


# ------------------------- business_status -------------------------
class TestInspectBusinessStatus:
    """响应体的业务成功/失败识别."""

    def test_non_dict_body_has_no_signal(self):
        assert inspect_business_status(None) is None
        assert inspect_business_status("plain text") is None
        assert inspect_business_status([1, 2]) is None
        assert inspect_business_status({}) is None

    def test_unrecognized_fields_have_no_signal(self):
        # 没有任何约定字段时不应凭空判定失败
        assert inspect_business_status({"hello": "world"}) is None

    @pytest.mark.parametrize("flag,expected_status", [
        ("f", "failed"),
        ("false", "failed"),
        ("F", "failed"),
        (False, "failed"),
        ("t", "passed"),
        ("true", "passed"),
        (True, "passed"),
    ])
    def test_flag_field(self, flag, expected_status):
        info = inspect_business_status({"flag": flag, "data": None})
        assert info is not None
        assert info["status"] == expected_status
        assert info["signal"] == "flag"

    @pytest.mark.parametrize("field", ["errorCode", "errCode", "error_code", "err_code"])
    def test_error_code_field_non_zero_means_failure(self, field):
        info = inspect_business_status({field: 100, "data": None})
        assert info is not None
        assert info["status"] == "failed"

    def test_error_code_zero_means_no_signal(self):
        # 0 表示无错误，不是「成功信号」，应继续往下看
        assert inspect_business_status({"errorCode": 0}) is None

    @pytest.mark.parametrize("code", [0, 200, "0", "200"])
    def test_business_code_success_values(self, code):
        info = inspect_business_status({"code": code})
        assert info is None  # 成功码不足以断言业务成功，只排除失败

    @pytest.mark.parametrize("code", [100, 500, "9999", 1])
    def test_business_code_non_success_with_empty_data_means_failure(self, code):
        info = inspect_business_status({"code": code, "data": None})
        assert info is not None
        assert info["status"] == "failed"
        assert info["signal"] == "code"

    @pytest.mark.parametrize("code", [1, 100])
    def test_non_standard_code_with_data_present_is_not_failure(self, code):
        """「1 表示成功」的接口：有数据返回时不因 code 非 0/200 判失败."""
        assert inspect_business_status({"code": code, "data": {"id": 1}}) is None

    def test_non_standard_code_with_error_message_means_failure(self):
        info = inspect_business_status(
            {"code": 500, "msg": "系统异常，请稍后重试", "data": {"x": 1}}
        )
        assert info is not None
        assert info["status"] == "failed"

    def test_status_text_field(self):
        failed = inspect_business_status({"status": "failed"})
        passed = inspect_business_status({"status": "success"})
        assert failed["status"] == "failed"
        assert passed["status"] == "passed"

    def test_error_info_with_empty_data_means_failure(self):
        info = inspect_business_status(
            {"errorInfo": "id not found", "data": None, "message": "id not found"}
        )
        assert info is not None
        assert info["status"] == "failed"

    def test_error_info_with_data_present_is_not_enough(self):
        # 有数据返回时，单独的 message 不足以判定失败
        assert inspect_business_status(
            {"errorInfo": "ok", "data": {"id": 1}}
        ) is None

    def test_explicit_flag_wins_over_code(self):
        info = inspect_business_status({"flag": "t", "code": 100})
        assert info["status"] == "passed"
        assert info["signal"] == "flag"


class TestBusinessStatusAssertion:
    """显式声明的 business_status 断言."""

    def test_failure_response_fails(self, engine):
        resp = ResponseData(
            status_code=200,
            body={"flag": "f", "errorCode": 100, "data": None},
        )
        rule = {"assertion_type": "business_status", "operator": "eq", "expected": "passed"}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is False
        assert result.actual == "failed"
        assert "失败" in result.message or "flag" in result.message

    def test_success_response_passes(self, engine):
        resp = ResponseData(status_code=200, body={"flag": "t", "data": {"id": 1}})
        rule = {"assertion_type": "business_status", "operator": "eq", "expected": "passed"}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is True

    def test_expecting_failure_passes_when_business_failed(self, engine):
        resp = ResponseData(status_code=200, body={"errorCode": 100})
        rule = {"assertion_type": "business_status", "operator": "eq", "expected": "failed"}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is True

    def test_no_recognizable_signal_fails_loudly(self, engine):
        resp = ResponseData(status_code=200, body={"hello": "world"})
        rule = {"assertion_type": "business_status", "operator": "eq", "expected": "passed"}
        result = engine.evaluate(resp, [rule])[0]
        assert result.passed is False
        assert "没有可识别" in result.message

    def test_evaluate_business_status_returns_none_without_signal(self, engine):
        assert engine.evaluate_business_status(
            ResponseData(status_code=200, body={"hello": "world"})
        ) is None

    def test_evaluate_business_status_returns_result_with_signal(self, engine):
        result = engine.evaluate_business_status(
            ResponseData(status_code=200, body={"flag": "f"})
        )
        assert result is not None
        assert result.assertion_type == "business_status"
        assert result.passed is False
