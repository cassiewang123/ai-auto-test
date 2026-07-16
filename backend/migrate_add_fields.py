"""数据库迁移脚本：为 API 测试增强功能补列.

新增字段：
- test_cases: retry_count, retry_interval, pre_script, post_script
- environments: cookies
- 新建表 global_variables（由 create_all 自动创建）

用法：在 backend 目录下运行 `python migrate_add_fields.py`
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# 定位 SQLite 数据库文件
DB_PATH = Path(__file__).resolve().parent / "aitest.db"


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    """检查某表的某列是否已存在."""
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def main() -> int:
    if not DB_PATH.exists():
        print(f"[错误] 数据库文件不存在: {DB_PATH}")
        print("请确认在 backend 目录下运行此脚本。")
        return 1

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    added = []

    # test_cases 新增列
    if table_exists(cur, "test_cases"):
        for col, ddl in [
            ("retry_count", "INTEGER DEFAULT 0"),
            ("retry_interval", "FLOAT DEFAULT 1.0"),
            ("pre_script", "TEXT"),
            ("post_script", "TEXT"),
        ]:
            if not column_exists(cur, "test_cases", col):
                cur.execute(f"ALTER TABLE test_cases ADD COLUMN {col} {ddl}")
                added.append(f"test_cases.{col}")
                print(f"[新增列] test_cases.{col}")
            else:
                print(f"[跳过] test_cases.{col} 已存在")

    # environments 新增列
    if table_exists(cur, "environments"):
        for col, ddl in [
            ("cookies", "JSON DEFAULT '[]'"),
        ]:
            if not column_exists(cur, "environments", col):
                cur.execute(f"ALTER TABLE environments ADD COLUMN {col} {ddl}")
                added.append(f"environments.{col}")
                print(f"[新增列] environments.{col}")
            else:
                print(f"[跳过] environments.{col} 已存在")
    else:
        print("[跳过] environments 表不存在")

    # global_variables 表通过 ORM create_all 创建，这里兜底手动建表
    if not table_exists(cur, "global_variables"):
        cur.execute(
            """
            CREATE TABLE global_variables (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name VARCHAR(128),
                value TEXT,
                var_type VARCHAR(16) DEFAULT 'string',
                description TEXT,
                scope VARCHAR(16) DEFAULT 'global',
                project_id VARCHAR(36),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL
            )
            """
        )
        cur.execute("CREATE INDEX ix_global_variables_name ON global_variables (name)")
        cur.execute("CREATE INDEX ix_global_variables_scope ON global_variables (scope)")
        cur.execute("CREATE INDEX ix_global_variables_project_id ON global_variables (project_id)")
        added.append("global_variables (新表)")
        print("[新增表] global_variables")
    else:
        print("[跳过] global_variables 表已存在")

    conn.commit()
    conn.close()

    print(f"\n迁移完成，共变更 {len(added)} 项: {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
