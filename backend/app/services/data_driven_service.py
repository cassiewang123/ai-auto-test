"""数据驱动测试服务：CSV/JSON 解析、变量替换、批量执行.

核心函数：
    parse_csv(csv_text)          -> list[dict]
    parse_json(json_text)        -> list[dict]
    extract_variables(data_rows) -> list[str]
    substitute_variables(template, variables_dict) -> 递归替换变量
    execute_data_driven(test_case, data_rows, environment) -> list[dict]

变量替换语法（FIX-07 统一）：
    - {{var}}  为标准语法（与 request_builder 统一）
    - ${var}   为兼容语法，后续将移除
在 url/headers/params/body 中递归替换为当前数据行的值。
"""

from __future__ import annotations

import copy
import csv
import io
import json
import re
from typing import Any

from app.services.security.data_redaction import redact_sensitive_data

# 变量替换正则
# {{var}} 为标准语法（与 request_builder 统一）
_VAR_PATTERN_STANDARD = re.compile(r"\{\{\s*(\w+)\s*\}\}")
# ${var} 为兼容语法，后续将移除
_VAR_PATTERN_LEGACY = re.compile(r"\$\{\s*(\w+)\s*\}")


def parse_csv(csv_text: str) -> list[dict[str, str]]:
    """解析 CSV 文本，第一行为表头，返回字典列表.

    自动跳过空行；支持引号包裹的字段（csv.DictReader 原生能力）。
    """
    if not csv_text or not csv_text.strip():
        return []
    reader = csv.DictReader(io.StringIO(csv_text))
    rows: list[dict[str, str]] = []
    for raw in reader:
        # DictReader 遇到空行可能返回全 None/空值的字典，跳过
        if any(v is not None and v != "" for v in raw.values()):
            rows.append(dict(raw))
    return rows


def parse_json(json_text: str) -> list[dict[str, Any]]:
    """解析 JSON 文本，要求为对象数组，返回字典列表.

    Raises:
        ValueError: JSON 不是数组，或数组元素不是对象。
        json.JSONDecodeError: JSON 格式错误。
    """
    if not json_text or not json_text.strip():
        return []
    data = json.loads(json_text)
    if not isinstance(data, list):
        raise ValueError("JSON 数据必须是数组")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"JSON 数组的第 {index} 个元素不是对象")
        result.append(item)
    return result


def extract_variables(data_rows: list[dict[str, Any]]) -> list[str]:
    """从数据行中提取变量名列表（所有键的并集，保持首次出现顺序）."""
    seen: set[str] = set()
    variables: list[str] = []
    for row in data_rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                variables.append(key)
    return variables


def substitute_variables(template: Any, variables_dict: dict[str, Any]) -> Any:
    """将变量替换为实际值，递归处理 dict/list/str.

    支持两种语法：
        - {{var}}  标准语法（推荐）
        - ${var}   兼容语法（后续将移除）

    未在 variables_dict 中找到的变量保持原样。
    """
    if isinstance(template, str):

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in variables_dict:
                return str(variables_dict[key])
            # 未知变量保持原样
            return match.group(0)

        # 先替换标准语法 {{var}}，再替换兼容语法 ${var}
        result = _VAR_PATTERN_STANDARD.sub(repl, template)
        result = _VAR_PATTERN_LEGACY.sub(repl, result)
        return result
    if isinstance(template, dict):
        return {k: substitute_variables(v, variables_dict) for k, v in template.items()}
    if isinstance(template, list):
        return [substitute_variables(v, variables_dict) for v in template]
    return template


def _headers_with_cookies(headers: dict, cookies: list[dict]) -> dict:
    """Build an outbound Cookie header from decrypted Cookie records."""
    result = dict(headers or {})
    pairs = [f"{cookie.get('name')}={cookie.get('value', '')}" for cookie in cookies if cookie.get("name")]
    if not pairs:
        return result
    existing = result.get("Cookie") or result.get("cookie") or ""
    cookie_header = "; ".join(pairs)
    result["Cookie"] = f"{existing}; {cookie_header}" if existing else cookie_header
    result.pop("cookie", None)
    return result


def execute_data_driven(
    test_case: Any,
    data_rows: list[dict[str, Any]],
    environment: Any | None = None,
) -> list[dict[str, Any]]:
    """遍历每行数据，替换变量，执行用例，收集结果.

    对每行数据：
        1. 合并环境变量 + 当前行数据（行数据优先）
        2. 替换 url/headers/params/body 中的 {{var}}（兼容 ${var}）
        3. 调用 TestCaseExecutor 执行请求与断言
        4. 记录行号、输入数据、响应状态、断言结果

    Args:
        test_case: TestCase ORM 模型实例。
        data_rows: 解析后的数据行列表。
        environment: 可选的 Environment ORM 模型实例，提供 base_url 与变量。

    Returns:
        每行数据的执行结果列表。
    """
    from test_engine.executor import TestCaseExecutor

    from app.schemas.execution import RequestDefinition

    executor = TestCaseExecutor()

    # 准备环境变量与 base_url
    env_vars: dict[str, Any] = {}
    base_url: str = ""
    environment_cookies: list[dict] = []
    if environment is not None:
        from app.services.security.secret_crypto import decrypt_cookies

        env_vars = dict(getattr(environment, "variables", None) or {})
        base_url = getattr(environment, "base_url", "") or ""
        environment_cookies = decrypt_cookies(getattr(environment, "cookies", None))

    # 准备断言列表（按 order 排序）
    assertions = []
    for a in sorted(getattr(test_case, "assertions", []) or [], key=lambda x: x.order):
        assertions.append(
            {
                "assertion_type": a.assertion_type,
                "expression": a.expression,
                "operator": a.operator,
                "expected": a.expected,
                "priority": a.priority,
                "order": a.order,
            }
        )

    results: list[dict[str, Any]] = []
    for index, row in enumerate(data_rows):
        # 合并变量：环境变量 + 当前行数据（行数据优先）
        merged_vars = {**env_vars, **row}

        # 替换变量（{{var}} 标准语法，兼容 ${var}）
        url = substitute_variables(test_case.url, merged_vars)
        headers = substitute_variables(dict(test_case.headers or {}), merged_vars)
        headers = _headers_with_cookies(headers, environment_cookies)
        params = substitute_variables(dict(test_case.params or {}), merged_vars)
        body = substitute_variables(copy.deepcopy(test_case.body), merged_vars) if test_case.body is not None else None

        # 处理相对 URL（环境 base_url 前缀）
        if base_url and not url.startswith("http"):
            url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"

        request_def = RequestDefinition(
            method=test_case.method,
            url=url,
            headers=headers,
            params=params,
            body=body,
            graphql_query=test_case.graphql_query,
            extract_rules=list(test_case.extract_rules or []),
            timeout=30.0,
        )

        try:
            result = executor.execute(
                request_def=request_def,
                assertions=assertions,
                variables={},
            )
            results.append(
                {
                    "row_index": index,
                    "input_data": redact_sensitive_data(
                        row,
                        parent_key="input_data",
                        transport_only=True,
                    ),
                    "status": result.status,
                    "duration": round(result.duration, 4),
                    "status_code": (result.response.status_code if result.response else None),
                    "assertion_results": [redact_sensitive_data(r.model_dump()) for r in result.assertion_results],
                    "error_message": redact_sensitive_data(result.error_message),
                    "url": url,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "row_index": index,
                    "input_data": redact_sensitive_data(
                        row,
                        parent_key="input_data",
                        transport_only=True,
                    ),
                    "status": "error",
                    "duration": 0,
                    "status_code": None,
                    "assertion_results": [],
                    "error_message": redact_sensitive_data(f"{type(exc).__name__}: {exc}"),
                    "url": url,
                }
            )

    return results
