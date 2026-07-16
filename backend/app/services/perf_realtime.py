"""压测实时指标内存存储（功能17）.

进程内字典存储每次压测的实时快照与状态，供轮询端点 /perf-tests/{id}/realtime 读取。
简化方案：不依赖 Redis，仅用内存字典（进程重启后丢失，符合本场景需求）。
"""
from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
# _store[test_id] = {
#   "run_id", "status" (running/completed/failed), "test_id",
#   "started_at", "snapshots": [{t, rps, avg_rt, error_rate, active_users,
#                                total_requests, fail_requests}], "result_id", "error"
# }
_store: dict[str, dict[str, Any]] = {}


def init_run(test_id: str, run_id: str) -> None:
    """初始化一次压测的实时存储."""
    with _lock:
        _store[test_id] = {
            "run_id": run_id,
            "status": "running",
            "test_id": test_id,
            "started_at": time.time(),
            "snapshots": [],
            "result_id": None,
            "error": None,
        }


def append_snapshot(test_id: str, snapshot: dict[str, Any]) -> None:
    """追加一帧实时快照."""
    with _lock:
        s = _store.get(test_id)
        if s is not None:
            # 限制快照数量，避免长压测内存膨胀
            if len(s["snapshots"]) < 3600:
                s["snapshots"].append(snapshot)


def set_status(
    test_id: str,
    status: str,
    result_id: str | None = None,
    error: str | None = None,
) -> None:
    """更新压测状态（completed/failed）。"""
    with _lock:
        s = _store.get(test_id)
        if s is not None:
            s["status"] = status
            if result_id is not None:
                s["result_id"] = result_id
            if error is not None:
                s["error"] = error


def get(test_id: str) -> dict[str, Any] | None:
    """读取某压测的实时状态（返回副本）。"""
    with _lock:
        s = _store.get(test_id)
        if s is None:
            return None
        # 返回副本，避免外部修改内部状态
        snap_copy = list(s["snapshots"])
        return {
            "run_id": s["run_id"],
            "status": s["status"],
            "test_id": s["test_id"],
            "started_at": s["started_at"],
            "snapshots": snap_copy,
            "result_id": s["result_id"],
            "error": s["error"],
        }


def clear(test_id: str) -> None:
    """清理某压测的实时存储。"""
    with _lock:
        _store.pop(test_id, None)
