"""性能测试增强功能数据库迁移脚本.

为已有 SQLite 数据库补列/建表，支持功能14-18：
- performance_results 新增 sla_status / sla_details / mode 列（功能16、功能14）
- perf_metrics 新表（功能15）：由 SQLAlchemy create_all 自动创建，此处兜底手动建表

用法（在 backend 目录执行）：
    python migrations/add_perf_enhancements.py

脚本幂等：列已存在则跳过，表已存在则跳过。

注意：本项目已迁移至 Alembic 管理数据库 schema（见 backend/alembic/）。
本脚本为历史遗留，保留用于向后兼容；新数据库变更请使用：
    cd backend && python -m alembic revision --autogenerate -m "描述"
    cd backend && python -m alembic upgrade head
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path 以便导入 app.config
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import get_settings  # noqa: E402


def _db_path() -> str:
    """从 DATABASE_URL 解析 SQLite 文件路径."""
    url = get_settings().DATABASE_URL
    # 形如 sqlite:///./aitest.db 或 sqlite:////abs/path.db
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "", 1)
    raise RuntimeError(f"仅支持 SQLite，当前 DATABASE_URL={url}")


def _column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def main() -> None:
    db_path = _db_path()
    print(f"[迁移] 数据库文件: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # performance_results 新增列
        for col, ddl in [
            ("sla_status", "ALTER TABLE performance_results ADD COLUMN sla_status VARCHAR(16)"),
            ("sla_details", "ALTER TABLE performance_results ADD COLUMN sla_details JSON"),
            ("mode", "ALTER TABLE performance_results ADD COLUMN mode VARCHAR(16)"),
        ]:
            if _table_exists(cur, "performance_results") and not _column_exists(
                cur, "performance_results", col
            ):
                cur.execute(ddl)
                print(f"[迁移] performance_results 新增列: {col}")
            else:
                print(f"[迁移] 跳过 performance_results.{col}（已存在或表不存在）")

        # perf_metrics 新表（兜底创建，create_all 通常已建好）
        if not _table_exists(cur, "perf_metrics"):
            cur.execute(
                """
                CREATE TABLE perf_metrics (
                    id VARCHAR(36) PRIMARY KEY,
                    test_id VARCHAR(36) NOT NULL,
                    run_id VARCHAR(36) NOT NULL,
                    result_id VARCHAR(36),
                    elapsed FLOAT DEFAULT 0.0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    cpu FLOAT DEFAULT 0.0,
                    memory FLOAT DEFAULT 0.0,
                    disk_read FLOAT DEFAULT 0.0,
                    disk_write FLOAT DEFAULT 0.0,
                    net_sent FLOAT DEFAULT 0.0,
                    net_recv FLOAT DEFAULT 0.0
                )
                """
            )
            cur.execute(
                "CREATE INDEX ix_perf_metrics_test_id ON perf_metrics (test_id)"
            )
            cur.execute(
                "CREATE INDEX ix_perf_metrics_run_id ON perf_metrics (run_id)"
            )
            cur.execute(
                "CREATE INDEX ix_perf_metrics_result_id ON perf_metrics (result_id)"
            )
            print("[迁移] 创建表: perf_metrics")
        else:
            print("[迁移] 跳过表 perf_metrics（已存在）")

        conn.commit()
        print("[迁移] 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
