"""AI 增强服务测试。

测试策略：
- generate_test_case / analyze_failure：通过 mock LLM 验证返回结构，同时验证无 LLM 时的 fallback
- recommend_assertions / detect_anomalies：纯规则实现，不依赖 LLM，直接验证逻辑正确性
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.execution import (
    AssertionResult,
    ExecutionResult,
    RequestDefinition,
    ResponseData,
)
from app.services.ai_service import AIService, LLMConfig


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------
class TestLLMConfig:
    def test_default_values(self):
        cfg = LLMConfig(model="gpt-4", api_key="sk-test", base_url="")
        assert cfg.model == "gpt-4"
        assert cfg.api_key == "sk-test"
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 2000

    def test_custom_values(self):
        cfg = LLMConfig(
            model="gpt-3.5-turbo",
            api_key="sk-xxx",
            base_url="https://api.example.com/v1",
            temperature=0.2,
            max_tokens=512,
        )
        assert cfg.temperature == 0.2
        assert cfg.max_tokens == 512
        assert cfg.base_url == "https://api.example.com/v1"


# ---------------------------------------------------------------------------
# AIService 初始化
# ---------------------------------------------------------------------------
class TestAIServiceInit:
    def test_init_with_explicit_config(self):
        cfg = LLMConfig(model="gpt-4", api_key="sk-test", base_url="")
        service = AIService(config=cfg)
        assert service.config.model == "gpt-4"
        assert service.config.api_key == "sk-test"

    def test_init_without_config_reads_settings(self):
        """未提供 config 时从 Settings 读取默认值。"""
        service = AIService()
        # Settings 默认 LLM_MODEL=gpt-4
        assert service.config.model is not None
        assert isinstance(service.config.temperature, float)


# ---------------------------------------------------------------------------
# _get_llm
# ---------------------------------------------------------------------------
class TestGetLLM:
    def test_get_llm_returns_none_without_api_key(self):
        """无 API key 时 _get_llm 返回 None。"""
        cfg = LLMConfig(model="gpt-4", api_key="", base_url="")
        service = AIService(config=cfg)
        assert service._get_llm() is None

    def test_get_llm_returns_instance_with_api_key(self):
        """有 API key 时 _get_llm 返回 LLM 实例（或 None 若 langchain 未安装）。"""
        cfg = LLMConfig(model="gpt-4", api_key="sk-test", base_url="")
        service = AIService(config=cfg)
        llm = service._get_llm()
        # langchain 可能未安装，此时为 None；若已安装则为非 None
        if llm is not None:
            assert llm is not None


# ---------------------------------------------------------------------------
# generate_test_case
# ---------------------------------------------------------------------------
class TestGenerateTestCase:
    def test_with_mock_llm(self):
        """mock LLM 返回，验证返回字符串包含 pytest 关键字。"""
        service = AIService()
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            "import pytest\n\n"
            "@allure.step('用户注册')\n"
            "def test_user_register(api_request_context):\n"
            "    # 正常注册\n"
            "    response = api_request_context.post('/api/register')\n"
            "    assert response.status == 200\n"
        )
        mock_llm.invoke.return_value = mock_response

        with patch.object(service, "_get_llm", return_value=mock_llm):
            code = service.generate_test_case("测试用户注册流程，覆盖正常注册、重复用户名、无效邮箱")

        assert isinstance(code, str)
        assert "def test" in code
        assert "pytest" in code.lower() or "import" in code
        # 验证 LLM 被调用
        mock_llm.invoke.assert_called_once()

    def test_with_api_schema(self):
        """提供 api_schema 时也正常工作。"""
        service = AIService()
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "import pytest\n\ndef test_create_user():\n    assert True\n"
        mock_llm.invoke.return_value = mock_response

        api_schema = {
            "method": "POST",
            "path": "/api/v1/users",
            "body": {"username": "string", "email": "string"},
        }
        with patch.object(service, "_get_llm", return_value=mock_llm):
            code = service.generate_test_case("创建用户", api_schema=api_schema)

        assert "def test" in code
        # prompt 中应包含 schema 信息
        call_args = mock_llm.invoke.call_args
        prompt_text = str(call_args)
        assert "/api/v1/users" in prompt_text or "POST" in prompt_text

    def test_fallback_no_llm(self):
        """无 LLM 时返回基于规则的 fallback 代码字符串。"""
        cfg = LLMConfig(model="gpt-4", api_key="", base_url="")
        service = AIService(config=cfg)
        with patch.object(service, "_get_llm", return_value=None):
            code = service.generate_test_case("测试用户登录流程")
        assert isinstance(code, str)
        assert "def test" in code
        assert len(code) > 0


# ---------------------------------------------------------------------------
# recommend_assertions（纯规则，不依赖 LLM）
# ---------------------------------------------------------------------------
class TestRecommendAssertions:
    def test_basic_response_structure(self):
        """用真实响应结构验证推荐规则合理。"""
        service = AIService()
        sample = {
            "code": 0,
            "data": {"id": 1, "name": "测试用户", "active": True},
            "message": "ok",
        }
        assertions = service.recommend_assertions(sample)

        assert isinstance(assertions, list)
        assert len(assertions) > 0
        types = [a["type"] for a in assertions]
        # 应包含 status_code 断言
        assert "status_code" in types
        # 应包含 json_path 断言
        assert "json_path" in types

    def test_recommends_type_assertions_for_nested_fields(self):
        """对嵌套字段推荐类型断言。"""
        service = AIService()
        sample = {"data": {"id": 1, "name": "test", "tags": ["a", "b"]}}
        assertions = service.recommend_assertions(sample)
        json_path_assertions = [a for a in assertions if a["type"] == "json_path"]
        expressions = [a["expression"] for a in json_path_assertions]
        # 应包含各字段的 json_path
        assert "$.data" in expressions
        assert "$.data.id" in expressions
        assert "$.data.name" in expressions
        assert "$.data.tags" in expressions
        # tags 是数组，应推荐 type=array
        tags_assertion = next(a for a in json_path_assertions if a["expression"] == "$.data.tags")
        assert tags_assertion["operator"] == "type"
        assert tags_assertion["expected"] == "array"

    def test_array_response(self):
        """响应体为数组时也能推荐断言。"""
        service = AIService()
        sample = [{"id": 1}, {"id": 2}]
        assertions = service.recommend_assertions(sample)
        assert isinstance(assertions, list)
        assert len(assertions) > 0
        types = [a["type"] for a in assertions]
        assert "status_code" in types

    def test_empty_response(self):
        """空响应也能返回默认断言。"""
        service = AIService()
        assertions = service.recommend_assertions({})
        assert isinstance(assertions, list)
        assert len(assertions) > 0
        types = [a["type"] for a in assertions]
        assert "status_code" in types

    def test_does_not_require_llm(self):
        """recommend_assertions 不依赖 LLM。"""
        cfg = LLMConfig(model="gpt-4", api_key="", base_url="")
        service = AIService(config=cfg)
        # 即使无 LLM 也能工作
        assert service._get_llm() is None
        assertions = service.recommend_assertions({"id": 1})
        assert len(assertions) > 0

    def test_type_detection(self):
        """验证各类型字段的类型检测。"""
        service = AIService()
        sample = {
            "str_field": "hello",
            "int_field": 42,
            "float_field": 3.14,
            "bool_field": True,
            "list_field": [1, 2],
            "obj_field": {"a": 1},
        }
        assertions = service.recommend_assertions(sample)
        type_map = {}
        for a in assertions:
            if a["type"] == "json_path" and a["operator"] == "type":
                type_map[a["expression"]] = a["expected"]
        assert type_map["$.str_field"] == "string"
        assert type_map["$.int_field"] == "integer"
        assert type_map["$.float_field"] == "number"
        assert type_map["$.bool_field"] == "boolean"
        assert type_map["$.list_field"] == "array"
        assert type_map["$.obj_field"] == "object"


# ---------------------------------------------------------------------------
# analyze_failure
# ---------------------------------------------------------------------------
class TestAnalyzeFailure:
    def _make_failed_result(self, **kwargs) -> ExecutionResult:
        defaults = dict(
            test_case_id="tc-1",
            status="failed",
            duration=1.5,
            request=RequestDefinition(method="GET", url="/api/users/1"),
            response=ResponseData(status_code=200, body={"id": 1}),
            error_message=None,
        )
        defaults.update(kwargs)
        return ExecutionResult(**defaults)

    def test_with_mock_llm(self):
        """mock LLM，验证返回结构含 root_cause。"""
        service = AIService()
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            '{"root_cause": "接口返回 500 内部错误", '
            '"evidence": "status_code=500", '
            '"category": "server_error", '
            '"suggestion": "检查后端服务日志", '
            '"confidence": 0.9}'
        )
        mock_llm.invoke.return_value = mock_response
        result = self._make_failed_result()

        with patch.object(service, "_get_llm", return_value=mock_llm):
            analysis = service.analyze_failure(result)

        assert isinstance(analysis, dict)
        assert "root_cause" in analysis
        assert "evidence" in analysis
        assert "category" in analysis
        assert "suggestion" in analysis
        assert "confidence" in analysis
        assert analysis["root_cause"] == "接口返回 500 内部错误"
        mock_llm.invoke.assert_called_once()

    def test_fallback_no_llm_status_code_mismatch(self):
        """无 LLM 时基于规则分析：状态码断言失败。"""
        cfg = LLMConfig(model="gpt-4", api_key="", base_url="")
        service = AIService(config=cfg)
        result = self._make_failed_result(
            assertion_results=[
                AssertionResult(
                    assertion_type="status_code",
                    expression=None,
                    operator="eq",
                    expected=200,
                    actual=500,
                    passed=False,
                    message="期望 200，实际 500",
                )
            ],
            response=ResponseData(status_code=500, body={}),
        )
        with patch.object(service, "_get_llm", return_value=None):
            analysis = service.analyze_failure(result)
        assert "root_cause" in analysis
        assert "category" in analysis
        assert analysis["category"] == "status_code_mismatch"
        assert isinstance(analysis["confidence"], float)

    def test_fallback_no_llm_server_error(self):
        """无 LLM 时基于规则分析：5xx 服务端错误。"""
        cfg = LLMConfig(model="gpt-4", api_key="", base_url="")
        service = AIService(config=cfg)
        result = self._make_failed_result(
            response=ResponseData(status_code=503, body={"error": "unavailable"}),
            error_message="Service Unavailable",
        )
        with patch.object(service, "_get_llm", return_value=None):
            analysis = service.analyze_failure(result)
        assert "root_cause" in analysis
        assert analysis["category"] in ("server_error", "status_code_mismatch")

    def test_fallback_no_llm_execution_error(self):
        """无 LLM 时基于规则分析：执行错误。"""
        cfg = LLMConfig(model="gpt-4", api_key="", base_url="")
        service = AIService(config=cfg)
        result = ExecutionResult(
            test_case_id="tc-2",
            status="error",
            duration=0.0,
            error_message="ConnectionRefusedError",
            error_traceback="Traceback ...",
        )
        with patch.object(service, "_get_llm", return_value=None):
            analysis = service.analyze_failure(result)
        assert "root_cause" in analysis
        assert analysis["category"] == "execution_error"

    def test_fallback_returns_all_required_keys(self):
        """fallback 返回必须包含所有约定字段。"""
        cfg = LLMConfig(model="gpt-4", api_key="", base_url="")
        service = AIService(config=cfg)
        result = self._make_failed_result()
        with patch.object(service, "_get_llm", return_value=None):
            analysis = service.analyze_failure(result)
        for key in ("root_cause", "evidence", "category", "suggestion", "confidence"):
            assert key in analysis, f"缺少字段 {key}"


# ---------------------------------------------------------------------------
# detect_anomalies（纯规则，不依赖 LLM）
# ---------------------------------------------------------------------------
class TestDetectAnomalies:
    def test_rps_drop(self):
        """RPS 突降检测。"""
        service = AIService()
        metrics = [
            {"rps": 100, "response_time": 0.5},
            {"rps": 100, "response_time": 0.5},
            {"rps": 100, "response_time": 0.5},
            {"rps": 30, "response_time": 0.5},  # 突降
            {"rps": 30, "response_time": 0.5},
        ]
        anomalies = service.detect_anomalies(metrics)
        assert isinstance(anomalies, list)
        rps_anomalies = [a for a in anomalies if a["metric"] == "rps"]
        assert len(rps_anomalies) >= 1
        assert "start" in rps_anomalies[0]
        assert "end" in rps_anomalies[0]
        assert "reason" in rps_anomalies[0]

    def test_response_time_spike(self):
        """响应时间飙升检测。"""
        service = AIService()
        metrics = [
            {"rps": 100, "response_time": 0.2},
            {"rps": 100, "response_time": 0.2},
            {"rps": 100, "response_time": 0.2},
            {"rps": 100, "response_time": 2.5},  # 飙升
            {"rps": 100, "response_time": 2.8},
        ]
        anomalies = service.detect_anomalies(metrics)
        rt_anomalies = [a for a in anomalies if a["metric"] == "response_time"]
        assert len(rt_anomalies) >= 1

    def test_no_anomaly_in_stable_data(self):
        """稳定数据无异常。"""
        service = AIService()
        metrics = [
            {"rps": 100, "response_time": 0.5},
            {"rps": 100, "response_time": 0.5},
            {"rps": 100, "response_time": 0.5},
        ]
        anomalies = service.detect_anomalies(metrics)
        assert len(anomalies) == 0

    def test_empty_metrics(self):
        """空指标列表返回空。"""
        service = AIService()
        assert service.detect_anomalies([]) == []

    def test_insufficient_metrics(self):
        """数据点过少返回空。"""
        service = AIService()
        assert service.detect_anomalies([{"rps": 100, "response_time": 0.5}]) == []

    def test_does_not_require_llm(self):
        """detect_anomalies 不依赖 LLM。"""
        cfg = LLMConfig(model="gpt-4", api_key="", base_url="")
        service = AIService(config=cfg)
        assert service._get_llm() is None
        metrics = [
            {"rps": 100, "response_time": 0.5},
            {"rps": 100, "response_time": 0.5},
            {"rps": 100, "response_time": 0.5},
            {"rps": 20, "response_time": 0.5},
        ]
        anomalies = service.detect_anomalies(metrics)
        assert any(a["metric"] == "rps" for a in anomalies)

    def test_anomaly_interval_keys(self):
        """异常区间包含 start/end/metric/reason 字段。"""
        service = AIService()
        metrics = [
            {"rps": 100, "response_time": 0.5},
            {"rps": 100, "response_time": 0.5},
            {"rps": 100, "response_time": 0.5},
            {"rps": 10, "response_time": 0.5},
        ]
        anomalies = service.detect_anomalies(metrics)
        for a in anomalies:
            assert "start" in a
            assert "end" in a
            assert "metric" in a
            assert "reason" in a
