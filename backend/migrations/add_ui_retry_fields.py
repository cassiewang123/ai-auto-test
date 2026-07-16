"""UI 测试失败自动重试功能数据库迁移脚本.

为已有 SQLite 数据库补列，支持 UI 测试用例与套件的失败自动重试：
- ui_test_cases 新增 retry_count / retry_interval 列
- ui_test_suites 新增 retry_enabled 列
- ui_test_suite_runs 新增 retry_enabled / total_retries / retried_cases 列
- ui_test_records 新增 retry_attempts / final_attempt 列

用法（在 backend 目录执行）：
    python migrations/add_ui_retry_fields.py

脚本幂等：表不存在或列已存在均跳过。

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
        # ui_test_cases 新增列：失败重试配置
        for col, ddl in [
            ("retry_count", "ALTER TABLE ui_test_cases ADD COLUMN retry_count INTEGER DEFAULT 0"),
            ("retry_interval", "ALTER TABLE ui_test_cases ADD COLUMN retry_interval FLOAT DEFAULT 2.0"),
        ]:
            if _table_exists(cur, "ui_test_cases") and not _column_exists(
                cur, "ui_test_cases", col
            ):
                cur.execute(ddl)
                print(f"[迁移] ui_test_cases 新增列: {col}")
            else:
                print(f"[迁移] 跳过 ui_test_cases.{col}（已存在或表不存在）")

        # ui_test_suites 新增列：是否启用失败重试
        for col, ddl in [
            ("retry_enabled", "ALTER TABLE ui_test_suites ADD COLUMN retry_enabled BOOLEAN DEFAULT 1"),
        ]:
            if _table_exists(cur, "ui_test_suites") and not _column_exists(
                cur, "ui_test_suites", col
            ):
                cur.execute(ddl)
                print(f"[迁移] ui_test_suites 新增列: {col}")
            else:
                print(f"[迁移] 跳过 ui_test_suites.{col}（已存在或表不存在）")

        # ui_test_suite_runs 新增列：重试统计
        for col, ddl in [
            ("retry_enabled", "ALTER TABLE ui_test_suite_runs ADD COLUMN retry_enabled BOOLEAN DEFAULT 1"),
            ("total_retries", "ALTER TABLE ui_test_suite_runs ADD COLUMN total_retries INTEGER DEFAULT 0"),
            ("retried_cases", "ALTER TABLE ui_test_suite_runs ADD COLUMN retried_cases JSON DEFAULT '[]'"),
        ]:
            if _table_exists(cur, "ui_test_suite_runs") and not _column_exists(
                cur, "ui_test_suite_runs", col
            ):
                cur.execute(ddl)
                print(f"[迁移] ui_test_suite_runs 新增列: {col}")
            else:
                print(f"[迁移] 跳过 ui_test_suite_runs.{col}（已存在或表不存在）")

        # ui_test_records 新增列：重试记录
        for col, ddl in [
            ("retry_attempts", "ALTER TABLE ui_test_records ADD COLUMN retry_attempts JSON DEFAULT '[]'"),
            ("final_attempt", "ALTER TABLE ui_test_records ADD COLUMN final_attempt INTEGER DEFAULT 1"),
        ]:
            if _table_exists(cur, "ui_test_records") and not _column_exists(
                cur, "ui_test_records", col
            ):
                cur.execute(ddl)
                print(f"[迁移] ui_test_records 新增列: {col}")
            else:
                print(f"[迁移] 跳过 ui_test_records.{col}（已存在或表不存在）")

        conn.commit()
        print("[迁移] 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
