"""Phase 4 数据库迁移脚本：Mock 增强 / UI 定位器 / 用例版本管理.

为已有 SQLite 数据库补列/建表，支持 Phase 4 三个功能扩展：
- mock_configs 新增：response_template / match_rules / priority / stateful_config / fault_injection
- test_cases 新增：version / case_status / reviewer_id / approved_by / published_at / parent_case_id
- ui_locators 新建表（元素定位器版本管理）

用法（在 backend 目录执行）：
    python migrations/add_phase4_fields.py

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
    print(f"[Phase 4 迁移] 数据库文件: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # === mock_configs 新增列（Phase 4 Mock 增强） ===
        mock_columns = [
            ("response_template", "ALTER TABLE mock_configs ADD COLUMN response_template TEXT"),
            ("match_rules", "ALTER TABLE mock_configs ADD COLUMN match_rules TEXT"),
            ("priority", "ALTER TABLE mock_configs ADD COLUMN priority INTEGER DEFAULT 0"),
            ("stateful_config", "ALTER TABLE mock_configs ADD COLUMN stateful_config TEXT"),
            ("fault_injection", "ALTER TABLE mock_configs ADD COLUMN fault_injection TEXT"),
        ]
        for col, ddl in mock_columns:
            if _table_exists(cur, "mock_configs") and not _column_exists(
                cur, "mock_configs", col
            ):
                cur.execute(ddl)
                print(f"[Phase 4 迁移] mock_configs 新增列: {col}")
            else:
                print(f"[Phase 4 迁移] 跳过 mock_configs.{col}（已存在或表不存在）")

        # === test_cases 新增列（Phase 4 用例版本管理） ===
        tc_columns = [
            ("version", "ALTER TABLE test_cases ADD COLUMN version INTEGER DEFAULT 1"),
            ("case_status", "ALTER TABLE test_cases ADD COLUMN case_status VARCHAR(20) DEFAULT 'draft'"),
            ("reviewer_id", "ALTER TABLE test_cases ADD COLUMN reviewer_id VARCHAR(36)"),
            ("approved_by", "ALTER TABLE test_cases ADD COLUMN approved_by VARCHAR(36)"),
            ("published_at", "ALTER TABLE test_cases ADD COLUMN published_at DATETIME"),
            ("parent_case_id", "ALTER TABLE test_cases ADD COLUMN parent_case_id VARCHAR(36)"),
        ]
        for col, ddl in tc_columns:
            if _table_exists(cur, "test_cases") and not _column_exists(
                cur, "test_cases", col
            ):
                cur.execute(ddl)
                print(f"[Phase 4 迁移] test_cases 新增列: {col}")
            else:
                print(f"[Phase 4 迁移] 跳过 test_cases.{col}（已存在或表不存在）")

        # 为 parent_case_id 创建索引（如果列已存在且索引不存在）
        if _table_exists(cur, "test_cases") and _column_exists(
            cur, "test_cases", "parent_case_id"
        ):
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_test_cases_parent_case_id'"
            )
            if not cur.fetchone():
                cur.execute(
                    "CREATE INDEX ix_test_cases_parent_case_id ON test_cases (parent_case_id)"
                )
                print("[Phase 4 迁移] 创建索引: ix_test_cases_parent_case_id")

        # 为 case_status 创建索引
        if _table_exists(cur, "test_cases") and _column_exists(
            cur, "test_cases", "case_status"
        ):
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_test_cases_case_status'"
            )
            if not cur.fetchone():
                cur.execute(
                    "CREATE INDEX ix_test_cases_case_status ON test_cases (case_status)"
                )
                print("[Phase 4 迁移] 创建索引: ix_test_cases_case_status")

        # === ui_locators 新建表（Phase 4 UI 定位器版本管理） ===
        if not _table_exists(cur, "ui_locators"):
            cur.execute(
                """
                CREATE TABLE ui_locators (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    project_id VARCHAR(36),
                    page_url VARCHAR(500),
                    selector_type VARCHAR(30) DEFAULT 'css',
                    selector_value VARCHAR(500) NOT NULL,
                    alternative_selectors TEXT,
                    description TEXT,
                    usage_count INTEGER DEFAULT 0,
                    last_used_at DATETIME,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                "CREATE INDEX ix_ui_locators_name ON ui_locators (name)"
            )
            cur.execute(
                "CREATE INDEX ix_ui_locators_project_id ON ui_locators (project_id)"
            )
            print("[Phase 4 迁移] 创建表: ui_locators")
        else:
            print("[Phase 4 迁移] 跳过 ui_locators（表已存在）")

        conn.commit()
        print("[Phase 4 迁移] 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
