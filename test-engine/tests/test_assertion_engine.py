"""断言引擎单元测试：覆盖 status_code / json_path / header / response_time / json_schema，
含通过、失败、边界与错误场景。"""
from __future__ import annotations

import pytest

from app.schemas.execution import ResponseData
from test_engine.assertion_engine import AssertionEngine


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
