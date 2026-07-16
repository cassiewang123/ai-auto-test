"""变量提取器：从 ResponseData 中按规则提取变量，合并到共享变量池.

支持的提取方式（rule["source"]）：
    - json_path / body: 用 jsonpath-ng 从 body 取值
    - regex:            用正则从 text（或字符串 body）取值
    - header:           从响应头取值（大小写不敏感）

规则格式：
    {"name": "token", "source": "json_path", "expression": "$.data.token"}
"""
from __future__ import annotations

import re
from typing import Any

from jsonpath_ng.ext import parse as jsonpath_parse

from app.schemas.execution import ResponseData


class VariableExtractor:
    """从响应数据中提取变量."""

    # body 与 json_path 视为同一种提取方式（兼容 TestCase 模型注释中的 source="body"）
    _JSONPATH_SOURCES = {"json_path", "body"}

    def extract(self, response: ResponseData, rules: list[dict]) -> dict[str, Any]:
        """按 rules 顺序提取变量，返回 {变量名: 值} 字典.

        - 未命中时对应变量值为 None，保证变量名始终存在于结果中。
        - 缺少 name 的规则会被安全跳过。
        """
        result: dict[str, Any] = {}
        for rule in rules:
            name = rule.get("name")
            if not name:
                continue
            source = (rule.get("source") or "").strip().lower()
            expression = rule.get("expression")
            try:
                value = self._extract_one(response, source, expression)
            except Exception:
                # 任何提取异常都降级为 None，避免单条规则中断整体提取
                value = None
            result[name] = value
        return result

    def _extract_one(self, response: ResponseData, source: str, expression: str | None) -> Any:
        if source in self._JSONPATH_SOURCES:
            return self._extract_jsonpath(response.body, expression)
        if source == "regex":
            return self._extract_regex(response, expression)
        if source == "header":
            return self._extract_header(response.headers, expression)
        # 未知 source
        return None

    # -- JSONPath --
    def _extract_jsonpath(self, body: Any, expression: str | None) -> Any:
        if not expression or not isinstance(body, (dict, list)):
            return None
        matches = [m.value for m in jsonpath_parse(expression).find(body)]
        if not matches:
            return None
        # 多个匹配取第一个
        return matches[0]

    # -- Regex --
    def _extract_regex(self, response: ResponseData, expression: str | None) -> Any:
        if not expression:
            return None
        # 优先用 text，text 为空时回退到字符串形式的 body
        haystack = response.text
        if not haystack:
            body = response.body
            if isinstance(body, str):
                haystack = body
            elif body is not None:
                haystack = str(body)
        match = re.search(expression, haystack)
        if not match:
            return None
        # 有捕获组时取第一个捕获组，否则取整体匹配
        if match.groups():
            return match.group(1)
        return match.group(0)

    # -- Header --
    def _extract_header(self, headers: dict[str, str], expression: str | None) -> Any:
        if not expression:
            return None
        target = expression.lower()
        for key, value in headers.items():
            if key.lower() == target:
                return value
        return None
