"""项目根目录 conftest：统一 sys.path 与导入模式.

背景：pytest.ini 的 testpaths 同时包含 backend/tests 和 test-engine/tests，
两个目录都有 __init__.py，在默认 prepend 模式下都被解析为同名包 "tests"，
导致 `python -m pytest`（裸跑）时发生包冲突：
    ModuleNotFoundError: No module named 'tests.test_xxx'

解决方案：
    1. 强制 importlib 导入模式 —— 每个测试模块按文件路径生成唯一模块名，
       不再依赖 sys.path 上的包名，从根本上消除同名包冲突。
    2. 提前把 backend/ 注入 sys.path —— importlib 模式不会像 prepend 模式
       那样自动把测试目录的父级加入 sys.path，因此 backend/tests/conftest.py
       中的 `from app...` 导入需要这里提前保障。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "backend"

# Unit tests must not inherit the developer's local Celery/Redis runtime mode.
os.environ["TASK_DISPATCH_MODE"] = "eager"
os.environ["TASK_FALLBACK_MODE"] = "eager"
os.environ["TASK_EAGER_IN_TESTS"] = "true"

# 单元测试绝不能真的调用外部大模型：
#   1. 会让测试变慢且不稳定（一次真实请求可能几十秒，还会被网络环境影响）；
#   2. 会把测试用的假需求发到第三方服务。
# 开发者本地一旦在 .env 打开 LLM_EXTERNAL_ENABLED，跑测试就会真的发请求，
# 因此这里强制关闭。需要验证 LLM 行为的用例，自行 monkeypatch 注入假客户端。
os.environ["LLM_EXTERNAL_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""

_p = str(_BACKEND)
if _p not in sys.path:
    sys.path.insert(0, _p)


def pytest_configure(config):
    """强制使用 importlib 导入模式，避免同名 tests 包冲突."""
    config.option.importmode = "importlib"
