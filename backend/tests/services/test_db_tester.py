"""数据库测试服务单元测试.

使用真实 SQLite（文件库，tmp_path 隔离）验证查询、断言与事务回滚隔离；
MySQL/PostgreSQL/MongoDB 仅验证 URL 构建（驱动延迟导入，不实际连接）。
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services.db_tester import DatabaseConfig, DatabaseTester


# ---------------------------------------------------------------------------
# fixture：初始化带数据的 SQLite 文件库
# ---------------------------------------------------------------------------
@pytest.fixture
def sqlite_env(tmp_path):
    db_path = tmp_path / "test.db"
    config = DatabaseConfig(db_type="sqlite", database=str(db_path))
    tester = DatabaseTester()
    engine = tester.create_connection(config)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)"
            )
        )
        conn.execute(text("INSERT INTO users (name, age) VALUES ('alice', 30)"))
        conn.execute(text("INSERT INTO users (name, age) VALUES ('bob', 25)"))
        conn.commit()
    engine.dispose()
    return config, tester


# ---------------------------------------------------------------------------
# 模型
# ---------------------------------------------------------------------------
class TestDatabaseConfig:
    def test_default_is_sqlite(self):
        config = DatabaseConfig()
        assert config.db_type == "sqlite"
        assert config.port is None

    def test_invalid_db_type_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DatabaseConfig(db_type="unsupported")


# ---------------------------------------------------------------------------
# URL 构建（多数据库）
# ---------------------------------------------------------------------------
class TestBuildUrl:
    def setup_method(self):
        self.tester = DatabaseTester()

    def test_sqlite_file(self):
        config = DatabaseConfig(db_type="sqlite", database="/tmp/x.db")
        url = self.tester.build_url(config)
        assert url.startswith("sqlite:")
        assert "x.db" in url

    def test_sqlite_in_memory(self):
        config = DatabaseConfig(db_type="sqlite", database="")
        url = self.tester.build_url(config)
        assert url == "sqlite://"

    def test_mysql_url(self):
        config = DatabaseConfig(
            db_type="mysql",
            host="h", port=3306, username="u", password="p", database="d",
        )
        url = self.tester.build_url(config)
        assert "mysql+pymysql" in url
        assert "u:p@h:3306" in url
        assert url.endswith("/d")

    def test_postgresql_url(self):
        config = DatabaseConfig(
            db_type="postgresql",
            host="h", port=5432, username="u", password="p", database="d",
        )
        url = self.tester.build_url(config)
        assert "postgresql+psycopg2" in url
        assert "h:5432" in url

    def test_mongodb_url(self):
        config = DatabaseConfig(
            db_type="mongodb",
            host="h", port=27017, username="u", password="p", database="d",
        )
        url = self.tester.build_url(config)
        assert url.startswith("mongodb://")
        assert "h:27017" in url


# ---------------------------------------------------------------------------
# SQLite 实际查询
# ---------------------------------------------------------------------------
class TestExecuteQuery:
    def test_returns_rows_as_dicts(self, sqlite_env):
        config, tester = sqlite_env
        rows = tester.execute_query(config, "SELECT id, name, age FROM users ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["name"] == "alice"
        assert rows[0]["age"] == 30
        assert rows[1]["name"] == "bob"

    def test_query_with_params(self, sqlite_env):
        config, tester = sqlite_env
        rows = tester.execute_query(
            config,
            "SELECT name FROM users WHERE age > :age",
            {"age": 26},
        )
        assert rows == [{"name": "alice"}]

    def test_empty_result(self, sqlite_env):
        config, tester = sqlite_env
        rows = tester.execute_query(config, "SELECT * FROM users WHERE age > 100")
        assert rows == []


# ---------------------------------------------------------------------------
# 断言
# ---------------------------------------------------------------------------
class TestAssertQuery:
    def test_eq_passes(self, sqlite_env):
        config, tester = sqlite_env
        assert tester.assert_query(config, "SELECT COUNT(*) FROM users", 2, "eq")

    def test_eq_fails(self, sqlite_env):
        config, tester = sqlite_env
        assert not tester.assert_query(config, "SELECT COUNT(*) FROM users", 99, "eq")

    def test_gt(self, sqlite_env):
        config, tester = sqlite_env
        assert tester.assert_query(config, "SELECT COUNT(*) FROM users", 1, "gt")
        assert not tester.assert_query(config, "SELECT COUNT(*) FROM users", 2, "gt")

    def test_lt(self, sqlite_env):
        config, tester = sqlite_env
        assert tester.assert_query(config, "SELECT COUNT(*) FROM users", 5, "lt")

    def test_ge_le(self, sqlite_env):
        config, tester = sqlite_env
        assert tester.assert_query(config, "SELECT COUNT(*) FROM users", 2, "ge")
        assert tester.assert_query(config, "SELECT COUNT(*) FROM users", 2, "le")

    def test_ne(self, sqlite_env):
        config, tester = sqlite_env
        assert tester.assert_query(config, "SELECT COUNT(*) FROM users", 3, "ne")

    def test_contains(self, sqlite_env):
        config, tester = sqlite_env
        assert tester.assert_query(
            config, "SELECT name FROM users WHERE id = 1", "ali", "contains"
        )

    def test_unknown_operator_raises(self, sqlite_env):
        config, tester = sqlite_env
        with pytest.raises(ValueError):
            tester.assert_query(config, "SELECT COUNT(*) FROM users", 2, "unknown")


# ---------------------------------------------------------------------------
# 事务回滚隔离
# ---------------------------------------------------------------------------
class TestTransactionIsolation:
    def test_execute_isolated_rolls_back(self, sqlite_env):
        config, tester = sqlite_env
        affected = tester.execute_isolated(
            config,
            "INSERT INTO users (name, age) VALUES ('charlie', 40)",
        )
        assert affected == 1
        # 回滚后数据不应持久化
        rows = tester.execute_query(config, "SELECT COUNT(*) AS c FROM users")
        assert rows[0]["c"] == 2

    def test_execute_isolated_update_rolls_back(self, sqlite_env):
        config, tester = sqlite_env
        affected = tester.execute_isolated(
            config,
            "UPDATE users SET age = 99 WHERE name = 'alice'",
        )
        assert affected == 1
        rows = tester.execute_query(
            config, "SELECT age FROM users WHERE name = 'alice'"
        )
        assert rows[0]["age"] == 30  # 未被修改

    def test_execute_isolated_delete_rolls_back(self, sqlite_env):
        config, tester = sqlite_env
        affected = tester.execute_isolated(config, "DELETE FROM users")
        assert affected == 2
        rows = tester.execute_query(config, "SELECT COUNT(*) AS c FROM users")
        assert rows[0]["c"] == 2  # 回滚后仍 2 条
