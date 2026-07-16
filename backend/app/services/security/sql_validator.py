"""SQL 安全校验：使用 sqlglot 解析 AST，防止危险操作.

SEC-07 改造：
- 通过 sqlglot 解析 SQL AST，禁止 INSERT/UPDATE/DELETE/DROP/CREATE/ALTER 等写操作
- 仅允许 SELECT（含 UNION / 子查询 / WITH-CTE）
- 禁止危险函数（LOAD_FILE / SLEEP / BENCHMARK 等）和 INTO 子句
- 提供 add_limit 自动补充行数限额，防止全表扫描
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp


class SQLValidationError(Exception):
    """SQL 安全校验失败。"""

    pass


# 禁止的 SQL 语句类型（写操作 / DDL / 命令）
FORBIDDEN_STATEMENT_TYPES = {
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Merge,
}

# 禁止的危险函数名
FORBIDDEN_FUNCTIONS = {
    "LOAD_FILE",
    "INTO_OUTFILE",
    "INTO_DUMPFILE",
    "BENCHMARK",
    "SLEEP",
    "EXEC",
    "EXECUTE",
    "xp_cmdshell",
}

# 允许的只读语句类型
_ALLOWED_TYPES = (exp.Select, exp.Union, exp.Subquery, exp.With)


def validate_sql(sql: str) -> str:
    """校验 SQL 语句安全性，返回清洗后的 SQL。

    校验规则：
    1. SQL 非空
    2. sqlglot 能成功解析（拒绝语法错误或多语句注入）
    3. 每条语句均为只读类型（SELECT / UNION / Subquery / With）
    4. 不包含禁止的语句类型（INSERT/UPDATE/DELETE/DROP 等）
    5. 不包含禁止的危险函数
    6. 不包含 INTO 子句（防止 INTO OUTFILE/DUMPFILE）
    """
    sql = sql.strip()
    if not sql:
        raise SQLValidationError("SQL 不能为空")

    try:
        parsed = sqlglot.parse(sql)
    except Exception as e:
        raise SQLValidationError(f"SQL 解析失败: {e}")

    if not parsed:
        raise SQLValidationError("SQL 解析结果为空")

    for stmt in parsed:
        if stmt is None:
            continue

        stmt_type = type(stmt)

        # 检查是否为禁止的语句类型
        if stmt_type in FORBIDDEN_STATEMENT_TYPES:
            raise SQLValidationError(
                f"禁止的 SQL 操作类型: {stmt_type.__name__}"
            )

        # 只允许 SELECT（含 WITH/CTE / UNION / 子查询）
        if not isinstance(stmt, _ALLOWED_TYPES):
            raise SQLValidationError(
                f"仅允许 SELECT 查询，当前类型: {stmt_type.__name__}"
            )

        # 检查禁止的函数（Anonymous 节点涵盖未特化的函数调用）
        for func in stmt.find_all(exp.Anonymous):
            func_name = func.name.upper()
            if func_name in FORBIDDEN_FUNCTIONS:
                raise SQLValidationError(f"禁止的函数: {func_name}")

        # 检查 INTO 子句（防止 INTO OUTFILE/DUMPFILE）
        for _ in stmt.find_all(exp.Into):
            raise SQLValidationError("禁止 INTO 子句")

    return sql


def add_limit(sql: str, max_rows: int = 1000) -> str:
    """如果 SQL 没有 LIMIT 子句，添加行数限制。

    防止无限制的全表扫描导致资源耗尽。
    """
    parsed = sqlglot.parse_one(sql)
    if not parsed.find(exp.Limit):
        return f"{sql.rstrip(';')} LIMIT {max_rows}"
    return sql
