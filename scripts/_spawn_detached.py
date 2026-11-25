"""以「完全脱离控制台」的方式启动子进程（Windows 用）.

为什么需要这个：`cmd.exe /c xxx` 会分配一个控制台，子进程挂在该控制台上。
宿主（终端、代理会话、WMI 包装进程）回收这个控制台时，附着在上面的控制台
程序（node.exe 等）会收到 CTRL_CLOSE_EVENT 并退出 —— 表现为「服务启动成功
后过一会儿自己没了，日志里却没有任何报错」。

DETACHED_PROCESS 让子进程不继承、也不新建任何控制台，因此不会再被控制台
事件波及。GUI 子系统的程序（pythonw.exe）本身不挂控制台，所以不受影响，
这也解释了为什么只有前端 node 反复退出。

用法：
    python _spawn_detached.py <workdir> <stdout_log> <stderr_log> -- <cmd> [args...]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print(
            "usage: _spawn_detached.py <workdir> <stdout_log> <stderr_log> -- <cmd> [...]",
            file=sys.stderr,
        )
        return 2

    split = argv.index("--")
    head, command = argv[:split], argv[split + 1 :]
    if len(head) != 3 or not command:
        print("工作目录、日志路径或启动命令不完整", file=sys.stderr)
        return 2

    workdir, stdout_path, stderr_path = head
    Path(stdout_path).parent.mkdir(parents=True, exist_ok=True)
    Path(stderr_path).parent.mkdir(parents=True, exist_ok=True)

    # 以追加方式打开日志，多次重启不会覆盖历史
    with open(stdout_path, "ab") as out, open(stderr_path, "ab") as err:
        process = subprocess.Popen(
            command,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            creationflags=DETACHED_PROCESS
            | CREATE_NEW_PROCESS_GROUP
            | CREATE_NO_WINDOW,
            close_fds=True,
        )
    print(process.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
