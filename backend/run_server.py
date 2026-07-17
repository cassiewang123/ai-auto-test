"""后端启动脚本：初始化 Windows WinSock 后启动 Uvicorn.

保持 Python 默认的 ProactorEventLoop；Playwright 在 Windows 上需要它创建
浏览器子进程。这里只提前初始化 WinSock，避免旧环境中的 WinError 10038。
"""
import os
import sys

if sys.platform == "win32":
    # 先创建一个 socket 触发 WinSock 初始化，避免 _overlapped 导入失败
    import _socket
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.close()
    except Exception:
        pass

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("AIRETEST_BACKEND_PORT", "8001"))
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        loop="asyncio",
    )
