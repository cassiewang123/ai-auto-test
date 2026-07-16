"""数据库迁移脚本：创建 4 张新表.

新增表：
- test_run_summaries   测试运行批次汇总
- scheduled_tasks      定时任务
- mock_configs         Mock 接口配置
- interface_change_logs 接口变更历史

使用 sqlite3 直接执行 CREATE TABLE IF NOT EXISTS，幂等可重复执行。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "aitest.db"

DDL_STATEMENTS = [
    # 1) 测试运行批次汇总
    """
    CREATE TABLE IF NOT EXISTS test_run_summaries (
        id VARCHAR(36) NOT NULL,
        run_id VARCHAR(36) NOT NULL,
        source VARCHAR(32) DEFAULT 'manual' NOT NULL,
        project_id VARCHAR(36),
        total INTEGER DEFAULT 0 NOT NULL,
        passed INTEGER DEFAULT 0 NOT NULL,
        failed INTEGER DEFAULT 0 NOT NULL,
        error INTEGER DEFAULT 0 NOT NULL,
        skipped INTEGER DEFAULT 0 NOT NULL,
        duration FLOAT DEFAULT 0.0 NOT NULL,
        triggered_by VARCHAR(128),
        scheduled_task_id VARCHAR(36),
        summary JSON,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (run_id),
        FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE SET NULL
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_test_run_summaries_run_id ON test_run_summaries (run_id)",
    # 2) 定时任务
    """
    CREATE TABLE IF NOT EXISTS scheduled_tasks (
        id VARCHAR(36) NOT NULL,
        name VARCHAR(128) NOT NULL,
        mode VARCHAR(16) DEFAULT 'interval' NOT NULL,
        schedule_config VARCHAR(256) NOT NULL,
        case_ids JSON,
        project_id VARCHAR(36),
        is_enabled BOOLEAN DEFAULT 1 NOT NULL,
        last_run_at DATETIME,
        last_run_status VARCHAR(16),
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE SET NULL
    )
    """,
    # 3) Mock 接口配置
    """
    CREATE TABLE IF NOT EXISTS mock_configs (
        id VARCHAR(36) NOT NULL,
        name VARCHAR(128) NOT NULL,
        method VARCHAR(16) DEFAULT 'GET' NOT NULL,
        path VARCHAR(512) NOT NULL,
        status_code INTEGER DEFAULT 200 NOT NULL,
        response_headers JSON,
        response_body TEXT,
        delay_ms INTEGER DEFAULT 0 NOT NULL,
        is_enabled BOOLEAN DEFAULT 1 NOT NULL,
        project_id VARCHAR(36),
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_mock_configs_path ON mock_configs (path)",
    # 4) 接口变更历史
    """
    CREATE TABLE IF NOT EXISTS interface_change_logs (
        id VARCHAR(36) NOT NULL,
        test_case_id VARCHAR(36) NOT NULL,
        action VARCHAR(16) NOT NULL,
        before JSON,
        after JSON,
        changed_fields JSON,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(test_case_id) REFERENCES test_cases (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_interface_change_logs_test_case_id ON interface_change_logs (test_case_id)",
]

NEW_TABLES = ["test_run_summaries", "scheduled_tasks", "mock_configs", "interface_change_logs"]


def main() -> int:
    if not DB_PATH.exists():
        print(f"[ERROR] 数据库文件不存在: {DB_PATH}", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        for stmt in DDL_STATEMENTS:
            cur.execute(stmt)
        con.commit()

        # 校验
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        existing = {r[0] for r in cur.fetchall()}
        missing = [t for t in NEW_TABLES if t not in existing]
        if missing:
            print(f"[ERROR] 以下表创建失败: {missing}", file=sys.stderr)
            return 2
        print("[OK] 迁移完成，新增表已就绪:")
        for t in NEW_TABLES:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [r[1] for r in cur.fetchall()]
            print(f"  - {t} ({len(cols)} 列): {', '.join(cols)}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
