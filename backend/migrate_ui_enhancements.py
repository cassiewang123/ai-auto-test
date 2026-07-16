"""数据库迁移：创建 UI 测试增强模块相关表.

新增表：
- visual_baselines: 视觉回归基线
- visual_diff_results: 视觉回归对比结果
- ui_test_suites: UI 测试套件
- ui_test_suite_runs: UI 测试套件执行记录
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "aitest.db"


def column_exists(cur, table: str, column: str) -> bool:
    """检查某表是否存在指定列."""
    try:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]
        return column in cols
    except sqlite3.Error:
        return False


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def migrate():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # ---- 视觉回归基线表 ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS visual_baselines (
        id VARCHAR(36) PRIMARY KEY,
        ui_test_case_id VARCHAR(36) NOT NULL REFERENCES ui_test_cases(id) ON DELETE CASCADE,
        name VARCHAR(256) NOT NULL,
        screenshot_path VARCHAR(512),
        baseline_image TEXT NOT NULL,
        threshold FLOAT DEFAULT 0.1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_visual_baselines_ui_test_case_id "
        "ON visual_baselines (ui_test_case_id)"
    )

    # ---- 视觉回归对比结果表 ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS visual_diff_results (
        id VARCHAR(36) PRIMARY KEY,
        ui_test_record_id VARCHAR(36) NOT NULL REFERENCES ui_test_records(id) ON DELETE CASCADE,
        baseline_id VARCHAR(36) NOT NULL REFERENCES visual_baselines(id) ON DELETE CASCADE,
        diff_score FLOAT DEFAULT 0.0,
        diff_image TEXT,
        passed BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_visual_diff_results_ui_test_record_id "
        "ON visual_diff_results (ui_test_record_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_visual_diff_results_baseline_id "
        "ON visual_diff_results (baseline_id)"
    )

    # ---- UI 测试套件表 ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ui_test_suites (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(256) NOT NULL,
        description TEXT,
        project_id VARCHAR(36) REFERENCES projects(id) ON DELETE SET NULL,
        case_ids JSON DEFAULT '[]',
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ui_test_suites_name ON ui_test_suites (name)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ui_test_suites_project_id "
        "ON ui_test_suites (project_id)"
    )

    # ---- UI 测试套件执行记录表 ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ui_test_suite_runs (
        id VARCHAR(36) PRIMARY KEY,
        suite_id VARCHAR(36) NOT NULL REFERENCES ui_test_suites(id) ON DELETE CASCADE,
        suite_name VARCHAR(256) NOT NULL,
        project_id VARCHAR(36),
        total INTEGER DEFAULT 0,
        passed INTEGER DEFAULT 0,
        failed INTEGER DEFAULT 0,
        duration FLOAT DEFAULT 0.0,
        status VARCHAR(16) DEFAULT 'running',
        record_ids JSON DEFAULT '[]',
        triggered_by VARCHAR(128) DEFAULT 'manual',
        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        finished_at DATETIME
    )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ui_test_suite_runs_suite_id "
        "ON ui_test_suite_runs (suite_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ui_test_suite_runs_project_id "
        "ON ui_test_suite_runs (project_id)"
    )

    conn.commit()
    conn.close()
    print(
        "Migration completed: visual_baselines, visual_diff_results, "
        "ui_test_suites, ui_test_suite_runs tables created."
    )


if __name__ == "__main__":
    migrate()
