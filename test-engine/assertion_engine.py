"""断言引擎：对 ResponseData 执行断言规则，返回 list[AssertionResult].

支持的断言类型（rule["assertion_type"]）：
    - status_code:      比较响应状态码
    - json_path:        用 jsonpath-ng 取值后比对
    - header:           检查响应头是否存在且匹配
    - response_time:    比较耗时是否 <= 阈值
    - json_schema:      用 jsonschema 校验 body 结构
    - business_status:  检查响应体里的业务成功/失败标志

操作符（rule["operator"]）：
    eq / ne / gt / lt / ge / le / contains / regex / type

规则格式：
    {"assertion_type": "json_path", "expression": "$.data.count",
     "operator": "eq", "expected": 5}

expected 兼容两种来源：
    - 直接值（int/dict/...）
    - JSON 编码文本（来自 ORM 的 Text 字段），会被自动解析

关于 business_status：
    很多接口出错时仍返回 HTTP 200，只在响应体里给出 flag/errorCode/code 等
    业务失败标志。只断言状态码时，这类失败会被误判为通过。执行器在「没有
    任何响应体断言」时会自动附加一项业务状态检查（详见 executor.py）；
    也可以显式添加：
        {"assertion_type": "business_status", "operator": "eq",
         "expected": "passed"}   # 期望业务成功
"""
from __future__ import annotations

import json
import operator as _op
import re
from typing import Any, Callable

from jsonpath_ng.ext import parse as jsonpath_parse
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError

from app.schemas.execution import AssertionResult, ResponseData


# 比较操作符 -> 内置函数
_NUMERIC_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": _op.eq,
    "ne": _op.ne,
    "gt": _op.gt,
    "lt": _op.lt,
    "ge": _op.ge,
    "le": _op.le,
}

# type 操作符期望的类型名映射
_TYPE_NAMES = {"int", "integer", "float", "number", "str", "string",
               "bool", "boolean", "list", "array", "dict", "object",
               "none", "null"}

# ---------------------------------------------------------------------------
# 业务状态检测：识别「HTTP 200 但业务失败」的响应体
# ---------------------------------------------------------------------------
# 布尔/标志类字段，取这些值表示失败或成功
_FLAG_FIELDS = ("flag", "success", "ok", "succeeded", "isSuccess", "is_success")
_FAILURE_FLAG_TEXT = {"f", "false", "0", "no", "n", "fail", "failed",
                      "error", "failure", "err"}
_SUCCESS_FLAG_TEXT = {"t", "true", "1", "yes", "y", "ok", "success",
                      "passed", "pass", "succeed", "成功"}

# 非零即失败的错误码字段（约定这类字段 0 表示无错误）
_ERROR_CODE_FIELDS = ("errorcode", "errcode", "error_code", "err_code",
                      "error_no", "errorno", "retcode", "ret_code")

# 通用业务码字段：约定 0 / 200 表示成功
_CODE_FIELDS = ("code", "statuscode", "status_code", "bizcode", "biz_code")
_SUCCESS_CODES = {0, 200, "0", "200"}

# 文本状态字段
_STATUS_FIELDS = ("status", "result", "state")
_FAILURE_STATUS_TEXT = {"fail", "failed", "failure", "error", "err",
                        "异常", "失败"}
_SUCCESS_STATUS_TEXT = {"success", "ok", "passed", "pass", "succeed",
                        "正常", "成功"}

# 错误描述字段：非空且 data 为空时视为失败
_ERROR_MESSAGE_FIELDS = ("errorinfo", "error_info", "errmsg", "err_msg",
                         "errormessage", "error_message", "errordesc",
                         "error_desc")


def _normalized_key_map(body: dict) -> dict[str, Any]:
    """把 body 的键统一成小写，便于匹配不同命名风格（errorCode / error_code）."""
    return {str(key).lower(): value for key, value in body.items()}


def _as_flag_state(value: Any) -> str | None:
    """把标志位归一化为 'passed' / 'failed'，无法判断时返回 None."""
    if isinstance(value, bool):
        return "passed" if value else "failed"
    if isinstance(value, (int, float)):
        return "passed" if value else "failed"
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _FAILURE_FLAG_TEXT:
            return "failed"
        if text in _SUCCESS_FLAG_TEXT:
            return "passed"
    return None


def _as_number(value: Any) -> float | None:
    """把数字或数字字符串转成 float，失败返回 None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def inspect_business_status(body: Any) -> dict[str, Any] | None:
    """检查响应体的业务状态，返回检测结果；无法判断时返回 None.

    返回形如 ``{"status": "failed", "signal": "flag", "message": "..."}``，
    status 为 ``passed`` / ``failed``。按「显式标志 > 错误码 > 业务码 >
    状态文本 > 错误描述」的优先级判断，先命中者为准。

    只识别约定俗成的字段，识别不到就返回 None，不会凭空判失败。
    """
    if not isinstance(body, dict) or not body:
        return None
    lower = _normalized_key_map(body)

    # 1) 显式布尔标志位
    for field in _FLAG_FIELDS:
        if field.lower() in lower:
            value = lower[field.lower()]
            state = _as_flag_state(value)
            if state is not None:
                if state == "failed":
                    return {
                        "status": "failed",
                        "signal": field,
                        "message": f"业务标志 {field}={value!r} 表示失败",
                    }
                return {
                    "status": "passed",
                    "signal": field,
                    "message": f"业务标志 {field}={value!r} 表示成功",
                }

    # 2) 错误码字段：非 0 即失败
    for field in _ERROR_CODE_FIELDS:
        if field in lower:
            number = _as_number(lower[field])
            if number is not None and number != 0:
                return {
                    "status": "failed",
                    "signal": field,
                    "message": f"错误码 {field}={lower[field]!r} 非 0",
                }

    # 3) 通用业务码：0 / 200 视为成功
    for field in _CODE_FIELDS:
        if field in lower:
            value = lower[field]
            number = _as_number(value)
            if number is not None and value not in _SUCCESS_CODES:
                return {
                    "status": "failed",
                    "signal": field,
                    "message": f"业务码 {field}={value!r} 不为 0/200",
                }

    # 4) 文本状态字段
    for field in _STATUS_FIELDS:
        if field in lower and isinstance(lower[field], str):
            text = lower[field].strip().lower()
            if text in _FAILURE_STATUS_TEXT:
                return {
                    "status": "failed",
                    "signal": field,
                    "message": f"业务状态 {field}={lower[field]!r} 表示失败",
                }
            if text in _SUCCESS_STATUS_TEXT:
                return {
                    "status": "passed",
                    "signal": field,
                    "message": f"业务状态 {field}={lower[field]!r} 表示成功",
                }

    # 5) 有错误描述且没有返回数据
    for field in _ERROR_MESSAGE_FIELDS:
        if field in lower:
            message = lower[field]
            if isinstance(message, str) and message.strip() and body.get("data") is None:
                return {
                    "status": "failed",
                    "signal": field,
                    "message": f"{field}={message.strip()!r} 且 data 为空",
                }

    return None


class AssertionEngine:
    """对响应数据执行断言评估."""

    # ---------------- 公共 API ----------------
    def evaluate(self, response: ResponseData, assertions: list[dict]) -> list[AssertionResult]:
        """逐条执行断言，返回 AssertionResult 列表."""
        results: list[AssertionResult] = []
        for rule in assertions:
            results.append(self._evaluate_one(response, rule))
        return results

    @staticmethod
    def all_passed(results: list[AssertionResult]) -> bool:
        """整体状态：空列表或全部通过为 True，任一失败为 False."""
        return all(r.passed for r in results)

    def evaluate_business_status(self, response: ResponseData) -> AssertionResult | None:
        """自动检查业务状态；识别不到任何业务标志时返回 None.

        供执行器在「用例没有响应体断言」时兜底调用：HTTP 200 不代表业务
        成功，识别到失败标志就产出一条失败断言，让整体状态变为 failed。
        通过时也返回结果，便于前端展示「已检查业务状态」；无信号则不打扰。
        """
        info = inspect_business_status(response.body)
        if info is None:
            return None
        return AssertionResult(
            assertion_type="business_status",
            expression=info["signal"],
            operator="eq",
            expected="passed",
            actual=info["status"],
            passed=info["status"] == "passed",
            message=info["message"],
        )

    # ---------------- 单条断言 ----------------
    def _evaluate_one(self, response: ResponseData, rule: dict) -> AssertionResult:
        assertion_type = rule.get("assertion_type", "")
        expression = rule.get("expression")
        operator_name = rule.get("operator", "eq")
        expected = self._normalize_expected(rule.get("expected"))

        base = dict(
            assertion_type=assertion_type,
            expression=expression if isinstance(expression, str) else (
                json.dumps(expression, ensure_ascii=False) if expression is not None else None
            ),
            operator=operator_name,
            expected=expected,
        )

        handler = self._HANDLERS.get(assertion_type)
        if handler is None:
            return AssertionResult(
                passed=False,
                message=f"不支持的断言类型: {assertion_type!r}",
                **base,
            )
        try:
            actual, passed, message = handler(self, response, expression, operator_name, expected)
        except Exception as exc:  # noqa: BLE001 - 断言不应中断整体流程
            return AssertionResult(
                passed=False,
                actual=None,
                message=f"断言执行异常: {exc}",
                **base,
            )
        return AssertionResult(passed=passed, actual=actual, message=message, **base)

    # ---------------- 类型分发 ----------------
    def _assert_status_code(self, response, expression, operator_name, expected):
        actual = response.status_code
        passed, message = self._compare(actual, operator_name, expected)
        return actual, passed, message

    def _assert_json_path(self, response, expression, operator_name, expected):
        actual = self._read_jsonpath(response.body, expression)
        if actual is None and operator_name != "ne":
            # 取不到值时，除 ne 外均判失败
            passed = operator_name == "ne" and expected is not None
            msg = "" if passed else f"JSONPath {expression!r} 未匹配到任何值"
            return actual, passed, msg
        passed, message = self._compare(actual, operator_name, expected)
        return actual, passed, message

    def _assert_header(self, response, expression, operator_name, expected):
        actual = self._read_header(response.headers, expression)
        if actual is None:
            return None, False, f"响应头 {expression!r} 不存在"
        passed, message = self._compare(actual, operator_name, expected)
        return actual, passed, message

    def _assert_response_time(self, response, expression, operator_name, expected):
        actual = response.elapsed
        passed, message = self._compare(actual, operator_name, expected)
        return actual, passed, message

    def _assert_json_schema(self, response, expression, operator_name, expected):
        schema = expected if expected is not None else expression
        schema = self._coerce_schema(schema)
        body = response.body
        # 若 body 不是 JSON 结构类型（如纯字符串），校验大概率失败
        validator = Draft7Validator(schema)
        try:
            validator.validate(body)
            return body, True, ""
        except SchemaValidationError as exc:
            return body, False, f"JSON Schema 校验失败: {exc.message}"

    def _assert_business_status(self, response, expression, operator_name, expected):
        """显式声明的业务状态断言：默认期望 business status 为 passed."""
        target = str(expected).strip().lower() if expected is not None else "passed"
        if target in _SUCCESS_FLAG_TEXT:
            target = "passed"
        elif target in _FAILURE_FLAG_TEXT:
            target = "failed"

        info = inspect_business_status(response.body)
        if info is None:
            return None, False, "响应体中没有可识别的业务状态标志（flag/success/errorCode/code 等）"
        actual = info["status"]
        passed = actual == target
        return actual, passed, "" if passed else f"{info['message']}（期望 {target}）"

    _HANDLERS = {
        "status_code": _assert_status_code,
        "json_path": _assert_json_path,
        "header": _assert_header,
        "response_time": _assert_response_time,
        "json_schema": _assert_json_schema,
        "business_status": _assert_business_status,
    }

    # ---------------- 比较核心 ----------------
    def _compare(self, actual: Any, operator_name: str, expected: Any) -> tuple[bool, str]:
        if operator_name in _NUMERIC_OPS:
            return self._compare_numeric(actual, operator_name, expected)
        if operator_name == "contains":
            return self._compare_contains(actual, expected)
        if operator_name == "regex":
            return self._compare_regex(actual, expected)
        if operator_name == "type":
            return self._compare_type(actual, expected)
        return False, f"不支持的操作符: {operator_name!r}"

    def _compare_numeric(self, actual, operator_name, expected):
        op = _NUMERIC_OPS[operator_name]
        # eq/ne 直接比较
        if operator_name in ("eq", "ne"):
            passed = op(actual, expected)
            return passed, "" if passed else self._fail_msg(operator_name, expected, actual)
        # gt/lt/ge/le 优先数值比较，失败则回退原生比较
        nums = self._try_float_pair(actual, expected)
        if nums is not None:
            a, e = nums
            passed = op(a, e)
        else:
            try:
                passed = op(actual, expected)
            except TypeError:
                return False, f"无法比较 {actual!r} 与 {expected!r}（类型不兼容）"
        return passed, "" if passed else self._fail_msg(operator_name, expected, actual)

    def _compare_contains(self, actual, expected):
        if isinstance(actual, list):
            passed = expected in actual
        elif isinstance(actual, str):
            passed = str(expected) in actual
        elif isinstance(actual, dict):
            passed = expected in actual  # 检查 key 是否存在
        else:
            passed = str(expected) in str(actual)
        return passed, "" if passed else f"期望包含 {expected!r}，实际 {actual!r}"

    def _compare_regex(self, actual, expected):
        try:
            passed = re.search(str(expected), str(actual)) is not None
        except re.error as exc:
            return False, f"无效正则表达式 {expected!r}: {exc}"
        return passed, "" if passed else f"{actual!r} 不匹配正则 {expected!r}"

    def _compare_type(self, actual, expected):
        type_name = str(expected).strip().lower()
        if type_name not in _TYPE_NAMES:
            return False, f"未知的类型名: {expected!r}"
        passed = self._check_type(actual, type_name)
        return passed, "" if passed else f"期望类型 {type_name!r}，实际 {type(actual).__name__!r}"

    # ---------------- 工具方法 ----------------
    @staticmethod
    def _check_type(value: Any, type_name: str) -> bool:
        if type_name in ("bool", "boolean"):
            return type(value) is bool
        if type_name in ("int", "integer"):
            return isinstance(value, int) and not isinstance(value, bool)
        if type_name in ("float",):
            return isinstance(value, float)
        if type_name in ("number",):
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if type_name in ("str", "string"):
            return isinstance(value, str)
        if type_name in ("list", "array"):
            return isinstance(value, list)
        if type_name in ("dict", "object"):
            return isinstance(value, dict)
        if type_name in ("none", "null"):
            return value is None
        return False

    @staticmethod
    def _try_float_pair(a, b):
        try:
            return float(a), float(b)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fail_msg(operator_name, expected, actual):
        return f"期望 {expected!r}（{operator_name}），实际 {actual!r}"

    @staticmethod
    def _normalize_expected(expected: Any) -> Any:
        """ORM 以 JSON 文本存储 expected，这里尝试解析；解析失败则保留原字符串."""
        if isinstance(expected, str):
            try:
                return json.loads(expected)
            except (json.JSONDecodeError, ValueError):
                return expected
        return expected

    @staticmethod
    def _coerce_schema(schema: Any) -> dict:
        if isinstance(schema, str):
            try:
                return json.loads(schema)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"无效的 JSON Schema 文本: {exc}") from exc
        if isinstance(schema, dict):
            return schema
        raise ValueError(f"无效的 JSON Schema: {schema!r}")

    @staticmethod
    def _read_jsonpath(body: Any, expression: str | None) -> Any:
        if not expression or not isinstance(body, (dict, list)):
            return None
        matches = [m.value for m in jsonpath_parse(expression).find(body)]
        if not matches:
            return None
        return matches[0]

    @staticmethod
    def _read_header(headers: dict[str, str], expression: str | None) -> str | None:
        if not expression:
            return None
        target = expression.lower()
        for key, value in headers.items():
            if key.lower() == target:
                return value
        return None
