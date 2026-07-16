"""测试执行引擎包.

REF-01: 将 test-engine 转为标准可导入包，通过
``pip install -e ./test-engine`` 安装后即可使用：

    from test_engine import TestCaseExecutor, RequestBuilder
    from test_engine.executor import TestCaseExecutor
    from test_engine.variable_extractor import VariableExtractor

注意：本包内部模块依赖 ``app.*``（backend 应用层），
因此需在 backend 运行环境中导入（``app`` 已在 sys.path 时）。
"""
from __future__ import annotations

from .assertion_engine import AssertionEngine
from .executor import TestCaseExecutor
from .request_builder import RequestBuilder
from .variable_extractor import VariableExtractor

__all__ = [
    "AssertionEngine",
    "RequestBuilder",
    "TestCaseExecutor",
    "VariableExtractor",
]

__version__ = "0.1.0"
