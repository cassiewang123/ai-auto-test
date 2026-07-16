"""数据库迁移：创建 UI 测试和性能测试相关表."""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "aitest.db"


def migrate():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # UI 测试用例表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ui_test_cases (
        id VARCHAR(36) PRIMARY KEY,
        title VARCHAR(256) NOT NULL,
        description TEXT,
        url VARCHAR(2048) NOT NULL,
        browser_type VARCHAR(32) DEFAULT 'chrome',
        steps JSON DEFAULT '[]',
        project_id VARCHAR(36) REFERENCES projects(id) ON DELETE SET NULL,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # UI 元素对象库表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ui_elements (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(128) NOT NULL,
        selector_type VARCHAR(32) DEFAULT 'css',
        selector_value VARCHAR(512) NOT NULL,
        page_url VARCHAR(2048),
        description TEXT,
        project_id VARCHAR(36) REFERENCES projects(id) ON DELETE SET NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 性能测试场景表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS performance_tests (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(256) NOT NULL,
        description VARCHAR(1024),
        case_ids JSON DEFAULT '[]',
        config JSON DEFAULT '{}',
        project_id VARCHAR(36) REFERENCES projects(id) ON DELETE SET NULL,
        status VARCHAR(16) DEFAULT 'idle',
        last_run_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 性能测试结果表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS performance_results (
        id VARCHAR(36) PRIMARY KEY,
        test_id VARCHAR(36) NOT NULL REFERENCES performance_tests(id) ON DELETE CASCADE,
        run_id VARCHAR(36) NOT NULL,
        total_requests INTEGER DEFAULT 0,
        success_requests INTEGER DEFAULT 0,
        fail_requests INTEGER DEFAULT 0,
        avg_response_time FLOAT DEFAULT 0.0,
        min_response_time FLOAT DEFAULT 0.0,
        max_response_time FLOAT DEFAULT 0.0,
        p50 FLOAT DEFAULT 0.0,
        p90 FLOAT DEFAULT 0.0,
        p95 FLOAT DEFAULT 0.0,
        p99 FLOAT DEFAULT 0.0,
        rps FLOAT DEFAULT 0.0,
        error_rate FLOAT DEFAULT 0.0,
        duration FLOAT DEFAULT 0.0,
        detail JSON DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    print("Migration completed: ui_test_cases, ui_elements, performance_tests, performance_results tables created.")


if __name__ == "__main__":
    migrate()
