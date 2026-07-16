"""AI 增强服务。

提供测试用例生成、断言推荐、失败分析与压测异常检测能力。

设计要点：
- langchain / openai 采用延迟导入，模块本身可在无 LLM 环境下正常导入。
- 所有依赖 LLM 的方法均有基于规则的 fallback，确保无 API key 时仍可用。
- recommend_assertions 与 detect_anomalies 为纯规则实现，不依赖 LLM，可独立测试。
"""
from __future__ import annotations

import json
import statistics
from typing import Any

from pydantic import BaseModel

from app.config import get_settings
from app.schemas.execution import ExecutionResult


class LLMConfig(BaseModel):
    """LLM 调用配置。"""

    model: str = "gpt-4"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 2000


class AIService:
    """AI 增强服务，封装测试相关的 LLM 与规则能力。"""

    def __init__(self, config: LLMConfig | None = None) -> None:
        """初始化服务，未提供 config 时从全局 Settings 读取。"""
        if config is None:
            settings = get_settings()
            config = LLMConfig(
                model=settings.LLM_MODEL,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.LLM_BASE_URL,
            )
        self.config = config

    # ------------------------------------------------------------------
    # LLM 实例获取（延迟导入）
    # ------------------------------------------------------------------
    def _get_llm(self) -> Any:
        """延迟导入并返回 ChatOpenAI 实例。

        若 langchain 未安装或未配置 api_key，则返回 None。
        """
        if not self.config.api_key:
            return None
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            return None

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "api_key": self.config.api_key,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        try:
            return ChatOpenAI(**kwargs)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 测试用例生成
    # ------------------------------------------------------------------
    def generate_test_case(
        self, description: str, api_schema: dict | None = None
    ) -> str:
        """根据自然语言描述生成 PyTest 用例代码字符串。"""
        llm = self._get_llm()
        if llm is None:
            return self._fallback_generate_test_case(description, api_schema)

        prompt = self._build_generate_prompt(description, api_schema)
        try:
            response = llm.invoke(prompt)
            return response.content
        except Exception:
            return self._fallback_generate_test_case(description, api_schema)

    def _build_generate_prompt(
        self, description: str, api_schema: dict | None
    ) -> str:
        """组装用例生成 prompt。"""
        prompt = (
            "你是一位资深测试工程师，请根据以下描述生成 PyTest 测试用例代码。\n\n"
            "要求:\n"
            "1. 使用 pytest 框架\n"
            "2. 使用 playwright 的 APIRequestContext 发起 HTTP 请求\n"
            "3. 覆盖正常场景和边界场景\n"
            "4. 断言充分\n"
            "5. 使用中文注释\n"
            "6. 使用 @allure.step 标注步骤\n\n"
            f"测试描述:\n{description}\n"
        )
        if api_schema:
            prompt += (
                "\n接口信息:\n"
                f"{json.dumps(api_schema, ensure_ascii=False, indent=2)}\n"
            )
        prompt += "\n请只返回 Python 代码，不要包含额外解释。"
        return prompt

    def _fallback_generate_test_case(
        self, description: str, api_schema: dict | None
    ) -> str:
        """无 LLM 时基于模板生成用例代码。"""
        method = "GET"
        path = "/api/v1/endpoint"
        if api_schema:
            method = api_schema.get("method", method)
            path = api_schema.get("path", api_schema.get("url", path))

        return (
            "import pytest\n"
            "import allure\n"
            "\n"
            "\n"
            f"@allure.step('自动生成用例: {description}')\n"
            "def test_generated_case(api_request_context):\n"
            f'    """自动生成的测试用例。\n\n'
            f"    描述: {description}\n"
            '    """\n'
            f"    # 接口: {method} {path}\n"
            "    # 正常场景\n"
            f"    response = api_request_context.{method.lower()}('{path}')\n"
            "    assert response.status == 200\n"
            "\n"
            "    # 边界场景: 待补充\n"
            "    # assert ...\n"
        )

    # ------------------------------------------------------------------
    # 断言推荐（纯规则，不依赖 LLM）
    # ------------------------------------------------------------------
    def recommend_assertions(self, response_sample: dict) -> list[dict]:
        """分析响应结构，推荐断言规则列表。"""
        assertions: list[dict] = [{"type": "status_code", "expected": 200}]
        self._walk_response(response_sample, "$", assertions, depth=0)
        return assertions

    def _walk_response(
        self,
        obj: Any,
        path: str,
        assertions: list[dict],
        depth: int,
    ) -> None:
        """递归遍历响应结构，生成 json_path 类型断言。"""
        if depth > 5:
            return

        if isinstance(obj, dict):
            assertions.append(
                {
                    "type": "json_path",
                    "expression": path,
                    "operator": "type",
                    "expected": "object",
                }
            )
            for key, value in obj.items():
                self._walk_response(value, f"{path}.{key}", assertions, depth + 1)
        elif isinstance(obj, list):
            assertions.append(
                {
                    "type": "json_path",
                    "expression": path,
                    "operator": "type",
                    "expected": "array",
                }
            )
            if obj:
                # 仅分析首个元素以代表数组元素结构
                self._walk_response(obj[0], f"{path}[0]", assertions, depth + 1)
        else:
            assertions.append(
                {
                    "type": "json_path",
                    "expression": path,
                    "operator": "type",
                    "expected": self._detect_type(obj),
                }
            )

    @staticmethod
    def _detect_type(value: Any) -> str:
        """推断 JSON 值的类型字符串。"""
        # 注意：bool 是 int 的子类，必须先判断
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "string"

    # ------------------------------------------------------------------
    # 失败分析
    # ------------------------------------------------------------------
    def analyze_failure(self, result: ExecutionResult) -> dict:
        """分析失败用例，返回根因、证据、分类、建议与置信度。"""
        llm = self._get_llm()
        if llm is None:
            return self._fallback_analyze_failure(result)

        prompt = self._build_analyze_prompt(result)
        try:
            response = llm.invoke(prompt)
            parsed = json.loads(response.content)
            return {
                "root_cause": parsed.get("root_cause", ""),
                "evidence": parsed.get("evidence", ""),
                "category": parsed.get("category", "unknown"),
                "suggestion": parsed.get("suggestion", ""),
                "confidence": float(parsed.get("confidence", 0.5)),
            }
        except Exception:
            return self._fallback_analyze_failure(result)

    def _build_analyze_prompt(self, result: ExecutionResult) -> str:
        """组装失败分析 prompt。"""
        payload = result.model_dump(mode="json")
        return (
            "你是资深测试工程师，请分析以下失败用例的执行结果，给出根因分析。\n\n"
            "请以 JSON 格式返回，包含字段: root_cause, evidence, category, "
            "suggestion, confidence(0-1)。\n\n"
            f"执行结果:\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n"
        )

    def _fallback_analyze_failure(self, result: ExecutionResult) -> dict:
        """无 LLM 时基于规则分析失败用例。"""
        # 1. 执行错误（异常中断）
        if result.status == "error" or (
            result.error_message and result.response is None
        ):
            return {
                "root_cause": result.error_message or "执行过程中发生异常",
                "evidence": result.error_traceback or result.error_message or "",
                "category": "execution_error",
                "suggestion": "检查目标服务可达性、网络连接与请求配置",
                "confidence": 0.7,
            }

        # 2. 断言失败
        failed = [a for a in result.assertion_results if not a.passed]
        if failed:
            sc_fail = [a for a in failed if a.assertion_type == "status_code"]
            if sc_fail:
                actual = sc_fail[0].actual
                expected = sc_fail[0].expected
                return {
                    "root_cause": f"状态码不匹配: 期望 {expected}, 实际 {actual}",
                    "evidence": sc_fail[0].message
                    or f"expected={expected}, actual={actual}",
                    "category": "status_code_mismatch",
                    "suggestion": "确认接口实现是否符合契约，或调整期望状态码",
                    "confidence": 0.8,
                }
            # 其他断言失败
            first = failed[0]
            return {
                "root_cause": f"断言失败: {first.assertion_type} "
                f"{first.expression or ''}",
                "evidence": first.message
                or f"expected={first.expected}, actual={first.actual}",
                "category": "response_field_mismatch",
                "suggestion": "检查响应字段类型与取值是否符合预期",
                "confidence": 0.6,
            }

        # 3. 基于响应状态码推断
        if result.response:
            sc = result.response.status_code
            if sc >= 500:
                return {
                    "root_cause": f"服务端错误: HTTP {sc}",
                    "evidence": f"status_code={sc}",
                    "category": "server_error",
                    "suggestion": "检查后端服务日志与依赖组件状态",
                    "confidence": 0.75,
                }
            if sc >= 400:
                return {
                    "root_cause": f"客户端错误: HTTP {sc}",
                    "evidence": f"status_code={sc}",
                    "category": "client_error",
                    "suggestion": "检查请求参数、鉴权与资源路径是否正确",
                    "confidence": 0.7,
                }

        # 4. 兜底
        return {
            "root_cause": "无法确定根本原因",
            "evidence": "无明确失败证据",
            "category": "unknown",
            "suggestion": "建议手动排查执行日志与响应详情",
            "confidence": 0.3,
        }

    # ------------------------------------------------------------------
    # 异常检测（纯规则，不依赖 LLM）
    # ------------------------------------------------------------------
    def detect_anomalies(self, metrics: list[dict]) -> list[dict]:
        """对压测指标时序数据做异常检测。

        检测 RPS 突降与响应时间飙升，返回异常区间列表。
        """
        if len(metrics) < 3:
            return []

        anomalies: list[dict] = []
        anomalies.extend(
            self._detect_metric_anomalies(
                metrics,
                name="rps",
                keys=("rps", "requests_per_second", "throughput"),
                direction="drop",
                ratio=0.5,
            )
        )
        anomalies.extend(
            self._detect_metric_anomalies(
                metrics,
                name="response_time",
                keys=(
                    "response_time",
                    "avg_response_time",
                    "rt",
                    "latency",
                    "p95",
                ),
                direction="spike",
                ratio=2.0,
            )
        )
        return anomalies

    def _detect_metric_anomalies(
        self,
        metrics: list[dict],
        name: str,
        keys: tuple[str, ...],
        direction: str,
        ratio: float,
    ) -> list[dict]:
        """对单一指标序列检测异常并合并连续区间。"""
        points: list[tuple[int, float]] = []
        for i, m in enumerate(metrics):
            value = None
            for k in keys:
                if k in m and m[k] is not None:
                    value = m[k]
                    break
            if value is not None:
                points.append((i, float(value)))

        if len(points) < 3:
            return []

        values = [v for _, v in points]
        baseline = statistics.median(values)
        if baseline <= 0:
            return []

        flags = [
            (v < baseline * ratio)
            if direction == "drop"
            else (v > baseline * ratio)
            for _, v in points
        ]

        intervals: list[dict] = []
        n = len(flags)
        i = 0
        while i < n:
            if flags[i]:
                start = i
                while i < n and flags[i]:
                    i += 1
                end = i - 1
                cur_val = points[start][1]
                if direction == "drop":
                    reason = (
                        f"{name} 突降: 当前值 {cur_val:.2f} 低于基准 "
                        f"{baseline:.2f} 的 {ratio * 100:.0f}%"
                    )
                else:
                    reason = (
                        f"{name} 飙升: 当前值 {cur_val:.2f} 超过基准 "
                        f"{baseline:.2f} 的 {ratio:.1f} 倍"
                    )
                intervals.append(
                    {
                        "start": points[start][0],
                        "end": points[end][0],
                        "metric": name,
                        "reason": reason,
                    }
                )
            else:
                i += 1
        return intervals

    # ------------------------------------------------------------------
    # 结构化用例生成（Multi-Agent 流程）
    # ------------------------------------------------------------------
    async def generate_structured_cases(
        self, source_type: str, source_data: dict, options: dict
    ) -> list[dict]:
        """生成结构化测试用例，直接可入库.

        Multi-Agent 流程：
        1. Agent 1: 测试点分析 - _analyze_test_points(source_type, source_data)
        2. Agent 2: 用例生成 - _generate_case_from_point(point, source_data)
        3. Agent 3: 断言推荐 - 复用现有 recommend_assertions 逻辑
        """
        points = self._analyze_test_points(source_type, source_data, options)
        cases: list[dict] = []
        for point in points:
            case = self._generate_case_from_point(point, source_data)
            cases.append(case)
        return cases

    def _analyze_test_points(
        self,
        source_type: str,
        source_data: dict,
        options: dict | None = None,
    ) -> list[dict]:
        """分析输入源，返回测试点列表.

        有 LLM 时调用 LLM 解析；无 LLM 时走 fallback 规则。
        返回示例: [{"point": "有效登录", "type": "normal", "priority": "P0"}, ...]
        """
        options = options or {}
        llm = self._get_llm()
        if llm is None:
            return self._fallback_analyze_test_points(source_type, source_data, options)

        prompt = self._build_analyze_points_prompt(source_type, source_data)
        try:
            response = llm.invoke(prompt)
            points = json.loads(response.content)
            if isinstance(points, list):
                max_cases = options.get("max_cases", 20)
                return points[:max_cases]
        except Exception:
            pass
        return self._fallback_analyze_test_points(source_type, source_data, options)

    def _build_analyze_points_prompt(
        self, source_type: str, source_data: dict
    ) -> str:
        """组装测试点分析 prompt."""
        return (
            "你是资深测试工程师，请分析以下输入源，提取测试点。\n\n"
            "返回 JSON 数组，每个元素包含: point(测试点描述), "
            "type(normal/exception/boundary), priority(P0-P3)。\n\n"
            f"输入类型: {source_type}\n"
            f"输入数据:\n{json.dumps(source_data, ensure_ascii=False, indent=2)}\n"
        )

    def _fallback_analyze_test_points(
        self,
        source_type: str,
        source_data: dict,
        options: dict | None = None,
    ) -> list[dict]:
        """无 LLM 时基于规则生成测试点."""
        options = options or {}
        points: list[dict] = []
        if source_type == "interface":
            method = source_data.get("method", "GET")
            points.append(
                {"point": f"{method}正常请求", "type": "normal", "priority": "P0"}
            )
            points.append(
                {"point": "参数缺失", "type": "exception", "priority": "P1"}
            )
            points.append(
                {"point": "参数边界值", "type": "boundary", "priority": "P1"}
            )
        else:
            # description / har / 其他均使用通用测试点
            points.append(
                {"point": "正常场景", "type": "normal", "priority": "P0"}
            )
            points.append(
                {"point": "异常场景", "type": "exception", "priority": "P1"}
            )
            points.append(
                {"point": "边界场景", "type": "boundary", "priority": "P1"}
            )

        max_cases = options.get("max_cases", 20)
        return points[:max_cases]

    def _generate_case_from_point(
        self, point: dict, source_data: dict
    ) -> dict:
        """为单个测试点生成结构化用例.

        有 LLM 时调用 LLM 生成；无 LLM 时走 fallback。
        """
        llm = self._get_llm()
        if llm is None:
            return self._fallback_generate_case_from_point(point, source_data)

        prompt = self._build_case_from_point_prompt(point, source_data)
        try:
            response = llm.invoke(prompt)
            case = json.loads(response.content)
            if isinstance(case, dict):
                # 确保必要字段存在
                case.setdefault("title", point.get("point", ""))
                case.setdefault("method", source_data.get("method", "POST"))
                case.setdefault(
                    "url",
                    source_data.get("url", source_data.get("path", "/api/v1/endpoint")),
                )
                case.setdefault("headers", {})
                case.setdefault("body", {})
                case.setdefault("assertions", [])
                case.setdefault("case_type", point.get("type", "normal"))
                case.setdefault("priority", point.get("priority", "P1"))
                case.setdefault("description", f"自动生成: {point.get('point', '')}")
                return case
        except Exception:
            pass
        return self._fallback_generate_case_from_point(point, source_data)

    def _build_case_from_point_prompt(
        self, point: dict, source_data: dict
    ) -> str:
        """组装用例生成 prompt."""
        return (
            "你是资深测试工程师，请根据测试点生成结构化测试用例。\n\n"
            "返回 JSON 对象，包含字段: title, case_type, priority, method, url, "
            "headers, body, assertions(数组，每项含 type/expected), description。\n\n"
            f"测试点:\n{json.dumps(point, ensure_ascii=False, indent=2)}\n\n"
            f"输入数据:\n{json.dumps(source_data, ensure_ascii=False, indent=2)}\n"
        )

    def _fallback_generate_case_from_point(
        self, point: dict, source_data: dict
    ) -> dict:
        """无 LLM 时基于模板生成结构化用例."""
        method = source_data.get("method", "POST")
        url = source_data.get("url", source_data.get("path", "/api/v1/endpoint"))
        case_type = point.get("type", "normal")

        if case_type == "exception":
            assertions: list[dict] = [
                {"type": "status_code", "expected": "400"}
            ]
            body: Any = {}
        else:
            # normal 与 boundary 均期望 200
            assertions = [{"type": "status_code", "expected": "200"}]
            body = source_data.get("body", {})

        return {
            "title": point.get("point", case_type),
            "case_type": case_type,
            "priority": point.get("priority", "P1"),
            "method": method,
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "assertions": assertions,
            "description": f"自动生成: {point.get('point', case_type)}",
        }
