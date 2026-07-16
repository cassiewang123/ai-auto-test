"""测试引擎共享 fixture 与路径配置.

REF-01: test-engine 现已作为 ``airetest-engine`` 包安装（见 test-engine/pyproject.toml），
导入方式统一为：

    from test_engine.executor import TestCaseExecutor
    from test_engine.request_builder import RequestBuilder

本 conftest 仅需将 backend 目录加入 sys.path，使测试代码可写：

    from app.schemas.execution import RequestDefinition, ResponseData, ...
"""
from __future__ import annotations

import sys
from pathlib import Path

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# backend 目录（包含 app 包）
_BACKEND_DIR = _PROJECT_ROOT / "backend"

for _path in (_BACKEND_DIR,):
    _p = str(_path)
    if _p not in sys.path:
        sys.path.insert(0, _p)
