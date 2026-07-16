"""测试用例脚本字段与会话 Cookie 迁移脚本.

为已有 SQLite 数据库补列，支持前置/后置脚本、失败重试与环境 Cookie 会话：
- test_cases 新增 retry_count / retry_interval / pre_script / post_script 列
- environments 新增 cookies 列

用法（在 backend 目录执行）：
    python migrations/add_test_case_script_fields.py

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
        # test_cases 新增列
        for col, ddl in [
            ("retry_count", "ALTER TABLE test_cases ADD COLUMN retry_count INTEGER DEFAULT 0"),
            ("retry_interval", "ALTER TABLE test_cases ADD COLUMN retry_interval FLOAT DEFAULT 1.0"),
            ("pre_script", "ALTER TABLE test_cases ADD COLUMN pre_script TEXT"),
            ("post_script", "ALTER TABLE test_cases ADD COLUMN post_script TEXT"),
        ]:
            if _table_exists(cur, "test_cases") and not _column_exists(
                cur, "test_cases", col
            ):
                cur.execute(ddl)
                print(f"[迁移] test_cases 新增列: {col}")
            else:
                print(f"[迁移] 跳过 test_cases.{col}（已存在或表不存在）")

        # environments 新增列
        for col, ddl in [
            ("cookies", "ALTER TABLE environments ADD COLUMN cookies JSON DEFAULT '[]'"),
        ]:
            if _table_exists(cur, "environments") and not _column_exists(
                cur, "environments", col
            ):
                cur.execute(ddl)
                print(f"[迁移] environments 新增列: {col}")
            else:
                print(f"[迁移] 跳过 environments.{col}（已存在或表不存在）")

        conn.commit()
        print("[迁移] 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
