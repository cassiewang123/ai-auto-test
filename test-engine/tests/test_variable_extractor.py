"""变量提取器单元测试：覆盖 JSONPath / regex / header 提取，含正常与边界/错误场景。"""
from __future__ import annotations

import pytest

from app.schemas.execution import ResponseData
from test_engine.variable_extractor import VariableExtractor


@pytest.fixture
def extractor():
    return VariableExtractor()


# ----------------------------- JSONPath 提取 -----------------------------
class TestJsonPathExtraction:
    def test_extract_simple_token(self, extractor):
        resp = ResponseData(
            status_code=200,
            body={"data": {"token": "abc123"}, "code": 0},
            text='{"data": {"token": "abc123"}}',
        )
        rules = [{"name": "token", "source": "json_path", "expression": "$.data.token"}]
        result = extractor.extract(resp, rules)
        assert result == {"token": "abc123"}

    def test_extract_nested_value(self, extractor):
        resp = ResponseData(
            status_code=200,
            body={"user": {"profile": {"email": "a@b.com"}}},
        )
        rules = [{"name": "email", "source": "json_path", "expression": "$.user.profile.email"}]
        result = extractor.extract(resp, rules)
        assert result["email"] == "a@b.com"

    def test_extract_from_list_body(self, extractor):
        resp = ResponseData(
            status_code=200,
            body={"items": [{"id": 1}, {"id": 2}]},
        )
        rules = [{"name": "first_id", "source": "json_path", "expression": "$.items[0].id"}]
        result = extractor.extract(resp, rules)
        assert result["first_id"] == 1

    def test_extract_wildcard_returns_first(self, extractor):
        resp = ResponseData(
            status_code=200,
            body={"items": [{"id": 10}, {"id": 20}]},
        )
        rules = [{"name": "id", "source": "json_path", "expression": "$.items[*].id"}]
        result = extractor.extract(resp, rules)
        # 通配匹配多个时，取第一个匹配值
        assert result["id"] == 10

    def test_jsonpath_no_match_returns_none(self, extractor):
        resp = ResponseData(status_code=200, body={"data": {}})
        rules = [{"name": "missing", "source": "json_path", "expression": "$.not.exist"}]
        result = extractor.extract(resp, rules)
        assert result == {"missing": None}

    def test_jsonpath_on_non_dict_body(self, extractor):
        # body 不是 dict/列表时，JSONPath 无法匹配
        resp = ResponseData(status_code=200, body="plain string body", text="plain string body")
        rules = [{"name": "x", "source": "json_path", "expression": "$.foo"}]
        result = extractor.extract(resp, rules)
        assert result == {"x": None}

    def test_body_source_alias_for_jsonpath(self, extractor):
        # TestCase 模型注释中 source 写作 "body"，应等同于 json_path
        resp = ResponseData(status_code=200, body={"access_token": "tkn"})
        rules = [{"name": "token", "source": "body", "expression": "$.access_token"}]
        result = extractor.extract(resp, rules)
        assert result == {"token": "tkn"}


# ----------------------------- Regex 提取 -----------------------------
class TestRegexExtraction:
    def test_extract_with_capture_group(self, extractor):
        resp = ResponseData(
            status_code=200,
            body=None,
            text='<input name="csrf" value="csrf_token_99" />',
        )
        rules = [{"name": "csrf", "source": "regex", "expression": r'value="([^"]+)"'}]
        result = extractor.extract(resp, rules)
        assert result["csrf"] == "csrf_token_99"

    def test_extract_without_group_returns_whole_match(self, extractor):
        resp = ResponseData(status_code=200, body=None, text="session=SESSIONID123; path=/")
        rules = [{"name": "sid", "source": "regex", "expression": r"SESSIONID\d+"}]
        result = extractor.extract(resp, rules)
        assert result["sid"] == "SESSIONID123"

    def test_regex_no_match_returns_none(self, extractor):
        resp = ResponseData(status_code=200, body=None, text="nothing here")
        rules = [{"name": "x", "source": "regex", "expression": r"token=\d+"}]
        result = extractor.extract(resp, rules)
        assert result == {"x": None}

    def test_regex_falls_back_to_body_text_when_text_empty(self, extractor):
        # 当 text 为空但 body 是字符串时，应能从 body 文本中提取
        resp = ResponseData(status_code=200, body="key=VALUE42", text="")
        rules = [{"name": "k", "source": "regex", "expression": r"key=(\w+)"}]
        result = extractor.extract(resp, rules)
        assert result["k"] == "VALUE42"


# ----------------------------- Header 提取 -----------------------------
class TestHeaderExtraction:
    def test_extract_header_value(self, extractor):
        resp = ResponseData(
            status_code=200,
            headers={"Content-Type": "application/json", "X-Request-Id": "rid-1"},
        )
        rules = [{"name": "req_id", "source": "header", "expression": "X-Request-Id"}]
        result = extractor.extract(resp, rules)
        assert result["req_id"] == "rid-1"

    def test_extract_header_case_insensitive(self, extractor):
        resp = ResponseData(status_code=200, headers={"content-type": "application/json"})
        rules = [{"name": "ct", "source": "header", "expression": "Content-Type"}]
        result = extractor.extract(resp, rules)
        assert result["ct"] == "application/json"

    def test_header_not_found_returns_none(self, extractor):
        resp = ResponseData(status_code=200, headers={"Content-Type": "application/json"})
        rules = [{"name": "auth", "source": "header", "expression": "Authorization"}]
        result = extractor.extract(resp, rules)
        assert result == {"auth": None}


# ----------------------------- 多变量 / 边界 -----------------------------
class TestMultipleAndEdgeCases:
    def test_extract_multiple_variables_at_once(self, extractor):
        resp = ResponseData(
            status_code=200,
            headers={"X-Token": "hdr-tok"},
            body={"data": {"id": 7, "name": "alice"}},
            text='{"data": {"id": 7}}',
        )
        rules = [
            {"name": "id", "source": "json_path", "expression": "$.data.id"},
            {"name": "name", "source": "json_path", "expression": "$.data.name"},
            {"name": "hdr", "source": "header", "expression": "X-Token"},
        ]
        result = extractor.extract(resp, rules)
        assert result == {"id": 7, "name": "alice", "hdr": "hdr-tok"}

    def test_empty_rules_returns_empty_dict(self, extractor):
        resp = ResponseData(status_code=200, body={"a": 1})
        assert extractor.extract(resp, []) == {}

    def test_rule_missing_name_is_skipped(self, extractor):
        # 缺少 name 的规则应被安全跳过，不抛异常
        resp = ResponseData(status_code=200, body={"a": 1})
        rules = [{"source": "json_path", "expression": "$.a"}]
        result = extractor.extract(resp, rules)
        assert result == {}

    def test_unknown_source_returns_none(self, extractor):
        resp = ResponseData(status_code=200, body={"a": 1})
        rules = [{"name": "x", "source": "unknown_source", "expression": "$.a"}]
        result = extractor.extract(resp, rules)
        assert result == {"x": None}
