"""执行编排器：组合 请求构建→变量提取→断言评估→结果组装 的完整测试流程.

TestCaseExecutor.execute(request_def, assertions, variables) -> ExecutionResult

流程：
    1. 渲染变量并发送请求（RequestBuilder）
    2. 从响应中提取变量并合并到共享变量池（VariableExtractor）
    3. 执行断言评估（AssertionEngine）
    4. 组装 ExecutionResult

异常处理：请求/提取/断言过程中的异常被捕获，状态置为 "error"，
并记录 error_message 与 error_traceback。
"""
from __future__ import annotations

import time
import traceback
from typing import Any

from app.schemas.execution import (
    ExecutionResult,
    ExtractedVariable,
    RequestDefinition,
    ResponseData,
)
from .assertion_engine import AssertionEngine
from .request_builder import RequestBuilder
from .variable_extractor import VariableExtractor


class TestCaseExecutor:
    """单条测试用例的执行编排器."""

    # 避免被 pytest 误当作测试用例类收集（类名以 Test 开头）
    __test__ = False

    def __init__(
        self,
        request_builder: RequestBuilder | None = None,
        assertion_engine: AssertionEngine | None = None,
        variable_extractor: VariableExtractor | None = None,
    ) -> None:
        self.request_builder = request_builder or RequestBuilder()
        self.assertion_engine = assertion_engine or AssertionEngine()
        self.variable_extractor = variable_extractor or VariableExtractor()

    # ---------------- 公共 API ----------------
    def execute(
        self,
        request_def: RequestDefinition,
        assertions: list[dict] | None = None,
        variables: dict | None = None,
        test_case_id: str = "",
    ) -> ExecutionResult:
        """执行完整测试流程，返回 ExecutionResult."""
        start = time.perf_counter()
        assertions = assertions or []
        # 复制变量池，避免污染调用方
        pool: dict[str, Any] = dict(variables or {})

        response: ResponseData | None = None
        assertion_results = []
        extracted_variables: list[ExtractedVariable] = []
        error_message: str | None = None
        error_traceback: str | None = None
        status = "error"

        try:
            # 1. 渲染变量并发送请求
            response = self.request_builder.send(request_def, pool)

            # 2. 提取变量并合并到池
            extracted = self.variable_extractor.extract(response, request_def.extract_rules)
            pool.update(extracted)
            extracted_variables = self._to_extracted_variables(
                extracted, request_def.extract_rules
            )

            # 3. 断言评估
            assertion_results = self.assertion_engine.evaluate(response, assertions)
            status = "passed" if self.assertion_engine.all_passed(assertion_results) else "failed"
        except Exception as exc:  # noqa: BLE001 - 捕获所有异常以记录错误
            status = "error"
            error_message = f"{type(exc).__name__}: {exc}"
            error_traceback = traceback.format_exc()

        duration = time.perf_counter() - start
        return ExecutionResult(
            test_case_id=test_case_id,
            status=status,
            duration=duration,
            request=request_def,
            response=response,
            assertion_results=assertion_results,
            extracted_variables=extracted_variables,
            error_message=error_message,
            error_traceback=error_traceback,
        )

    # ---------------- 工具方法 ----------------
    @staticmethod
    def _to_extracted_variables(
        extracted: dict[str, Any], rules: list[dict]
    ) -> list[ExtractedVariable]:
        """把提取结果字典转为 ExtractedVariable 列表，保留来源信息."""
        source_map: dict[str, str] = {}
        for rule in rules or []:
            name = rule.get("name")
            if name:
                source_map[name] = rule.get("source", "body")
        return [
            ExtractedVariable(
                name=name,
                value=value,
                source=source_map.get(name, "body"),
            )
            for name, value in extracted.items()
        ]
