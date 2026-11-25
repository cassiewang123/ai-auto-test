"""后端启动脚本：初始化 Windows WinSock 后启动 Uvicorn.

保持 Python 默认的 ProactorEventLoop；Playwright 在 Windows 上需要它创建
浏览器子进程。这里只提前初始化 WinSock，避免旧环境中的 WinError 10038。

热重载：
    默认关闭（reload=False）。需要改完代码自动重启时，设置环境变量
    ``AIRETEST_RELOAD=1`` 再启动即可：

        PowerShell:  $env:AIRETEST_RELOAD=1; python backend\\run_server.py
        bash:        AIRETEST_RELOAD=1 python backend/run_server.py

    开启后只监听 backend 目录，避免把 frontend/node_modules 等一起纳入
    文件监控。默认关闭是因为自动重启会中断正在进行中的请求（例如长耗时
    的用例执行、性能测试），这些场景下稳定比自动重载更重要。
"""
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    # 先创建一个 socket 触发 WinSock 初始化，避免 _overlapped 导入失败
    import _socket
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.close()
    except Exception:
        pass

import uvicorn

# 以 app.main:app 的形式启动需要 backend 目录在 sys.path 上。
# 之前依赖「脚本所在目录自动进 sys.path」，一旦从别处启动就会导入失败；
# reload 模式会再起一个子进程，显式加进去更稳妥。
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    """读取布尔型环境变量，接受 1/true/yes/on（大小写不敏感）."""
    return (os.getenv(name) or "").strip().lower() in _TRUTHY


if __name__ == "__main__":
    port = int(os.getenv("AIRETEST_BACKEND_PORT", "8001"))
    reload_enabled = _env_flag("AIRETEST_RELOAD")

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        reload=reload_enabled,
        # 仅热重载时生效：只监听后端源码，别把前端 node_modules 也扫一遍
        reload_dirs=[str(APP_DIR)] if reload_enabled else None,
        reload_includes=["*.py"] if reload_enabled else None,
        loop="asyncio",
    )
