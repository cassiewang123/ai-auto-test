"""数据库测试服务.

支持 Oracle(python-oracledb) / MySQL(PyMySQL) / PostgreSQL(psycopg2) /
SQLite(内置) / MongoDB(pymongo)。
- Oracle/MySQL/PG/SQLite 走 SQLAlchemy create_engine
- MongoDB 走 pymongo（延迟导入）
- 写操作通过 execute_isolated 实现事务回滚隔离：begin → 执行 → rollback
"""
from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote, quote_plus

from pydantic import BaseModel
from sqlalchemy import create_engine, text


class DatabaseConfig(BaseModel):
    """数据库连接配置."""

    db_type: Literal["oracle", "mysql", "postgresql", "sqlite", "mongodb"] = "sqlite"
    host: str = "localhost"
    port: int | None = None
    username: str = ""
    password: str = ""
    database: str = ""
    driver: str = ""


class DatabaseTester:
    """数据库测试器：查询、断言、事务隔离."""

    _SUPPORTED_OPERATORS = {"eq", "ne", "gt", "lt", "ge", "le", "contains"}

    # ------------------------------------------------------------------
    # URL 构建
    # ------------------------------------------------------------------
    def build_url(self, config: DatabaseConfig) -> str:
        """根据 db_type 构建连接 URL（纯字符串，不触发驱动导入）."""
        if config.db_type == "sqlite":
            if not config.database:
                return "sqlite://"
            return f"sqlite:///{config.database}"

        if config.db_type == "oracle":
            auth = (
                f"{quote(config.username, safe='')}:"
                f"{quote(config.password, safe='')}@"
            )
            service_name = quote_plus(config.database)
            return (
                f"oracle+oracledb://{auth}{config.host}:{config.port or 1521}/"
                f"?service_name={service_name}"
            )

        auth = (
            f"{quote(config.username, safe='')}:"
            f"{quote(config.password, safe='')}@"
        )
        if config.db_type == "mysql":
            port = config.port or 3306
            return f"mysql+pymysql://{auth}{config.host}:{port}/{config.database}"
        if config.db_type == "postgresql":
            port = config.port or 5432
            return f"postgresql+psycopg2://{auth}{config.host}:{port}/{config.database}"
        if config.db_type == "mongodb":
            port = config.port or 27017
            return f"mongodb://{auth}{config.host}:{port}/{config.database}"

        raise ValueError(f"Unsupported db_type: {config.db_type}")

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    def create_connection(self, config: DatabaseConfig):
        """创建连接对象：SQLAlchemy Engine 或 pymongo MongoClient."""
        if config.db_type == "mongodb":
            # 延迟导入 pymongo
            from pymongo import MongoClient

            return MongoClient(self.build_url(config))

        url = self.build_url(config)
        connect_args: dict[str, Any] = {}
        if config.db_type == "sqlite":
            connect_args = {"check_same_thread": False}
            if not config.database:
                # 内存库需 StaticPool 才能在不同连接间共享数据
                from sqlalchemy.pool import StaticPool

                return create_engine(
                    "sqlite://",
                    connect_args=connect_args,
                    poolclass=StaticPool,
                )
        return create_engine(url, connect_args=connect_args)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def execute_query(
        self, config: DatabaseConfig, sql: str, params: dict | None = None
    ) -> list[dict]:
        """执行 SELECT，返回 list[dict]."""
        if config.db_type == "mongodb":
            return self._execute_mongodb(config, params)

        engine = self.create_connection(config)
        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                return [dict(row._mapping) for row in result.fetchall()]
        finally:
            engine.dispose()

    def _execute_mongodb(
        self, config: DatabaseConfig, params: dict | None
    ) -> list[dict]:
        """MongoDB 简单查询：params={"collection": ..., "query": {...}}."""
        from pymongo import MongoClient

        client = MongoClient(self.build_url(config))
        try:
            db = client[config.database]
            params = params or {}
            collection_name = params.get("collection")
            if not collection_name:
                return []
            query = params.get("query", {})
            return list(db[collection_name].find(query))
        finally:
            client.close()

    # ------------------------------------------------------------------
    # 事务回滚隔离
    # ------------------------------------------------------------------
    def execute_isolated(
        self, config: DatabaseConfig, sql: str, params: dict | None = None
    ) -> int:
        """事务回滚隔离：begin → 执行 → rollback，返回受影响行数.

        适用于 INSERT/UPDATE/DELETE 的“试运行”，确保不污染数据库。
        """
        engine = self.create_connection(config)
        conn = engine.connect()
        trans = conn.begin()
        try:
            result = conn.execute(text(sql), params or {})
            rowcount = result.rowcount
        finally:
            trans.rollback()
            conn.close()
            engine.dispose()
        return int(rowcount or 0)

    # ------------------------------------------------------------------
    # 断言
    # ------------------------------------------------------------------
    @staticmethod
    def _get_scalar(rows: list[dict]) -> Any:
        """取第一行第一列的标量值."""
        if not rows:
            return None
        first = rows[0]
        return list(first.values())[0]

    def _compare(self, actual: Any, expected: Any, operator: str) -> bool:
        if operator not in self._SUPPORTED_OPERATORS:
            raise ValueError(f"Unknown operator: {operator}")
        if operator == "eq":
            return bool(actual == expected)
        if operator == "ne":
            return bool(actual != expected)
        if operator == "gt":
            return bool(actual > expected)
        if operator == "lt":
            return bool(actual < expected)
        if operator == "ge":
            return bool(actual >= expected)
        if operator == "le":
            return bool(actual <= expected)
        if operator == "contains":
            return bool(expected in actual)
        return False  # 理论不可达

    def assert_query(
        self,
        config: DatabaseConfig,
        sql: str,
        expected: Any,
        operator: str = "eq",
    ) -> bool:
        """执行 SQL 并与期望值比对，返回是否通过."""
        rows = self.execute_query(config, sql)
        actual = self._get_scalar(rows)
        return self._compare(actual, expected, operator)
