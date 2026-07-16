"""可复用步骤组功能数据库迁移脚本（Page Object Model）.

新建 step_library 表，用于存储可复用步骤组，供 UI 测试用例通过
action="step_group" 引用。

用法（在 backend 目录执行）：
    python migrations/add_step_library.py

脚本幂等：表已存在则跳过。create_all 通常已自动建表，此处兜底手动建表。

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
        if not _table_exists(cur, "step_library"):
            cur.execute(
                """
                CREATE TABLE step_library (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    project_id VARCHAR(36),
                    steps JSON,
                    tags JSON,
                    usage_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL
                )
                """
            )
            cur.execute(
                "CREATE INDEX ix_step_library_name ON step_library (name)"
            )
            cur.execute(
                "CREATE INDEX ix_step_library_project_id ON step_library (project_id)"
            )
            print("[迁移] 创建表: step_library")
        else:
            print("[迁移] 跳过表 step_library（已存在）")

        conn.commit()
        print("[迁移] 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
