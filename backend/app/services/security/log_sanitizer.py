"""日志脱敏过滤器 (SEC-09).

作为 logging.Filter 挂载到 root logger，在日志输出前
自动将 password / token / secret / Authorization Bearer 等敏感信息替换为 ****。
"""
from __future__ import annotations

import logging
import re

# 敏感模式：(正则, 替换模板)
SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r'(password|passwd|pwd)["\']?\s*[:=]\s*["\']?[^"\',\s]+', re.I),
        r"\1=****",
    ),
    (
        re.compile(r'(token|api_key|apikey)["\']?\s*[:=]\s*["\']?[^"\',\s]+', re.I),
        r"\1=****",
    ),
    (
        re.compile(r'(secret)["\']?\s*[:=]\s*["\']?[^"\',\s]+', re.I),
        r"\1=****",
    ),
    (
        re.compile(r"(Authorization:\s*Bearer\s+)[^\s]+", re.I),
        r"\1****",
    ),
]


class SanitizingFilter(logging.Filter):
    """日志脱敏过滤器：拦截日志记录，替换敏感信息。"""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        for pattern, replacement in SENSITIVE_PATTERNS:
            msg = pattern.sub(replacement, msg)
        record.msg = msg
        # 清除已格式化的 args，避免重复拼接
        record.args = ()
        return True
