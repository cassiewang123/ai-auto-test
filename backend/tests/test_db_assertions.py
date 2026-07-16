"""数据库断言 CRUD API 测试."""
from __future__ import annotations

import pytest

import app.models  # noqa: F401  注册模型元数据

BASE = "/api/v1/db-assertions"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _create_test_case(client, **overrides):
    payload = {
        "title": "测试用例",
        "method": "GET",
        "url": "/api/ping",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/test-cases", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _create_environment(client, **overrides):
    payload = {
        "name": "测试环境",
        "base_url": "http://192.168.1.1:8080",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/environments", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _create_db_assertion(client, test_case_id, **overrides):
    payload = {
        "test_case_id": test_case_id,
        "name": "断言状态",
        "sql_template": "SELECT 1 as val",
        "expected_result": {"field": "val", "operator": "equals", "value": 1},
    }
    payload.update(overrides)
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------
class TestCreateDbAssertion:
    def test_create_db_assertion(self, client):
        case = _create_test_case(client)
        data = _create_db_assertion(
            client,
            test_case_id=case["id"],
            name="订单状态断言",
            sql_template="SELECT status FROM orders WHERE id = '{{order_id}}'",
            expected_result={"field": "status", "operator": "equals", "value": "paid"},
        )
        assert data["id"]
        assert data["test_case_id"] == case["id"]
        assert data["name"] == "订单状态断言"
        assert "status FROM orders" in data["sql_template"]
        assert data["expected_result"]["operator"] == "equals"
        assert data["is_active"] is True

    def test_create_with_defaults(self, client):
        case = _create_test_case(client)
        resp = client.post(BASE, json={
            "test_case_id": case["id"],
            "name": "默认断言",
            "sql_template": "SELECT 1",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["expected_result"] == {}
        assert data["is_active"] is True


# ---------------------------------------------------------------------------
# 列表查询
# ---------------------------------------------------------------------------
class TestListDbAssertions:
    def test_list_db_assertions(self, client):
        case = _create_test_case(client)
        _create_db_assertion(client, test_case_id=case["id"], name="断言1")
        _create_db_assertion(client, test_case_id=case["id"], name="断言2")

        resp = client.get(f"{BASE}?test_case_id={case['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert len(body["data"]) == 2

    def test_list_empty(self, client):
        case = _create_test_case(client)
        resp = client.get(f"{BASE}?test_case_id={case['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_filtered_by_case(self, client):
        case1 = _create_test_case(client, title="用例A")
        case2 = _create_test_case(client, title="用例B")
        _create_db_assertion(client, test_case_id=case1["id"], name="A断言")
        _create_db_assertion(client, test_case_id=case2["id"], name="B断言")

        resp = client.get(f"{BASE}?test_case_id={case1['id']}")
        assert len(resp.json()["data"]) == 1
        assert resp.json()["data"][0]["name"] == "A断言"


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------
class TestUpdateDbAssertion:
    def test_update_db_assertion(self, client):
        case = _create_test_case(client)
        assertion = _create_db_assertion(client, test_case_id=case["id"])

        resp = client.put(f"{BASE}/{assertion['id']}", json={
            "name": "更新名称",
            "sql_template": "SELECT 2 as val",
            "expected_result": {"field": "val", "operator": "equals", "value": 2},
            "is_active": False,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "更新名称"
        assert data["sql_template"] == "SELECT 2 as val"
        assert data["expected_result"]["value"] == 2
        assert data["is_active"] is False

    def test_update_partial(self, client):
        case = _create_test_case(client)
        assertion = _create_db_assertion(client, test_case_id=case["id"])

        resp = client.put(f"{BASE}/{assertion['id']}", json={"is_active": False})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_active"] is False
        # 未更新字段保留
        assert data["name"] == "断言状态"

    def test_update_not_found(self, client):
        resp = client.put(f"{BASE}/nonexistent", json={"name": "x"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------
class TestDeleteDbAssertion:
    def test_delete_db_assertion(self, client):
        case = _create_test_case(client)
        assertion = _create_db_assertion(client, test_case_id=case["id"])

        resp = client.delete(f"{BASE}/{assertion['id']}")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        # 删除后列表为空
        resp2 = client.get(f"{BASE}?test_case_id={case['id']}")
        assert resp2.json()["data"] == []

    def test_delete_not_found(self, client):
        resp = client.delete(f"{BASE}/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 级联删除：删除用例时级联删除断言
# ---------------------------------------------------------------------------
class TestCascadeDelete:
    def test_delete_cascades_with_case(self, client):
        case = _create_test_case(client)
        _create_db_assertion(client, test_case_id=case["id"], name="断言1")
        _create_db_assertion(client, test_case_id=case["id"], name="断言2")

        # 列表应有 2 条
        resp = client.get(f"{BASE}?test_case_id={case['id']}")
        assert len(resp.json()["data"]) == 2

        # 删除用例
        resp = client.delete(f"/api/v1/test-cases/{case['id']}")
        assert resp.status_code == 200

        # 级联删除后列表应为空（通过新用例同 ID 查询，断言已级联删除）
        # 由于 test_case_id 不再存在，直接查询应返回空
        resp = client.get(f"{BASE}?test_case_id={case['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# 测试 SQL 断言执行（内存 SQLite）
# ---------------------------------------------------------------------------
class TestTestDbAssertion:
    def test_test_db_assertion_with_sqlite(self, client):
        # 创建带 db_config 的环境（内存 SQLite）
        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="SELECT 1 as val",
            expected_result={"field": "val", "operator": "equals", "value": 1},
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["passed"] is True
        assert data["sql"] == "SELECT 1 as val LIMIT 1000"
        assert data["actual"] == 1

    def test_test_db_assertion_fails(self, client):
        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="SELECT 1 as val",
            expected_result={"field": "val", "operator": "equals", "value": 99},
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        assert data["actual"] == 1

    def test_test_db_assertion_with_variables(self, client):
        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="SELECT {{val}} as val",
            expected_result={"field": "val", "operator": "equals", "value": 42},
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
            json={"val": 42},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["passed"] is True
        # SEC-07: 参数绑定后 SQL 中使用 :val 占位符，值通过 params 传入
        assert ":val" in data["sql"]
        assert "LIMIT" in data["sql"]

    def test_test_db_assertion_rejects_non_select(self, client):
        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="DELETE FROM users",
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 422

    def test_test_db_assertion_count_operator(self, client):
        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="SELECT 1 UNION ALL SELECT 2",
            expected_result={"operator": "count", "value": 2},
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is True
        assert data["actual"] == 2

    def test_test_db_assertion_not_found(self, client):
        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        resp = client.post(
            f"{BASE}/nonexistent/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 404

    def test_test_db_assertion_env_not_found(self, client):
        case = _create_test_case(client)
        assertion = _create_db_assertion(client, test_case_id=case["id"])

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_test_db_assertion_no_db_config(self, client):
        # 创建不带 db_config 的环境
        env = _create_environment(client)
        case = _create_test_case(client)
        assertion = _create_db_assertion(client, test_case_id=case["id"])

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# SEC-07: 变量语法统一为 {{var}}，通过参数绑定防止注入
# ---------------------------------------------------------------------------
class TestBindVariablesSyntax:
    """直接测试 _bind_variables 函数，验证 {{var}} 参数绑定."""

    def test_binds_double_brace_var(self):
        from app.api.v1.db_assertions import _bind_variables

        sql, params = _bind_variables("SELECT {{val}} as v", {"val": 42})
        assert sql == "SELECT :val as v"
        assert params == {"val": 42}

    def test_binds_double_brace_with_spaces(self):
        from app.api.v1.db_assertions import _bind_variables

        sql, params = _bind_variables("SELECT {{ val }} as v", {"val": 42})
        assert sql == "SELECT :val as v"
        assert params == {"val": 42}

    def test_unknown_var_raises_error(self):
        """SEC-07: 未匹配的变量应抛出 ValidationError."""
        from app.api.v1.db_assertions import _bind_variables
        from app.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="未匹配的变量"):
            _bind_variables("SELECT {{unknown}} as v", {"val": 42})

    def test_multiple_vars_in_one_string(self):
        from app.api.v1.db_assertions import _bind_variables

        sql, params = _bind_variables(
            "SELECT {{a}}, {{b}}", {"a": 1, "b": 2}
        )
        assert sql == "SELECT :a, :b"
        assert params == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# SEC-07: SQL AST 校验直接测试
# ---------------------------------------------------------------------------
class TestSqlValidator:
    """直接测试 sql_validator 模块的校验逻辑."""

    def test_select_passes(self):
        from app.services.security.sql_validator import validate_sql

        assert validate_sql("SELECT 1") == "SELECT 1"

    def test_delete_rejected(self):
        from app.services.security.sql_validator import SQLValidationError, validate_sql

        with pytest.raises(SQLValidationError, match="禁止"):
            validate_sql("DELETE FROM users")

    def test_drop_rejected(self):
        from app.services.security.sql_validator import SQLValidationError, validate_sql

        with pytest.raises(SQLValidationError, match="禁止"):
            validate_sql("DROP TABLE users")

    def test_update_rejected(self):
        from app.services.security.sql_validator import SQLValidationError, validate_sql

        with pytest.raises(SQLValidationError, match="禁止"):
            validate_sql("UPDATE users SET name='x'")

    def test_multi_statement_rejected(self):
        """SEC-07: SELECT; DROP TABLE 多语句注入应被拒绝."""
        from app.services.security.sql_validator import SQLValidationError, validate_sql

        with pytest.raises(SQLValidationError, match="禁止"):
            validate_sql("SELECT * FROM t; DROP TABLE t")

    def test_sleep_function_rejected(self):
        from app.services.security.sql_validator import SQLValidationError, validate_sql

        with pytest.raises(SQLValidationError, match="禁止的函数"):
            validate_sql("SELECT SLEEP(5)")

    def test_union_passes(self):
        from app.services.security.sql_validator import validate_sql

        assert validate_sql("SELECT 1 UNION ALL SELECT 2") == "SELECT 1 UNION ALL SELECT 2"

    def test_cte_passes(self):
        from app.services.security.sql_validator import validate_sql

        sql = "WITH cte AS (SELECT 1) SELECT * FROM cte"
        assert validate_sql(sql) == sql

    def test_empty_sql_rejected(self):
        from app.services.security.sql_validator import SQLValidationError, validate_sql

        with pytest.raises(SQLValidationError, match="不能为空"):
            validate_sql("")

    def test_add_limit(self):
        from app.services.security.sql_validator import add_limit

        assert add_limit("SELECT 1") == "SELECT 1 LIMIT 1000"

    def test_add_limit_skips_existing(self):
        from app.services.security.sql_validator import add_limit

        assert add_limit("SELECT 1 LIMIT 10") == "SELECT 1 LIMIT 10"

    def test_add_limit_custom_max(self):
        from app.services.security.sql_validator import add_limit

        assert add_limit("SELECT 1", max_rows=500) == "SELECT 1 LIMIT 500"


# ---------------------------------------------------------------------------
# SEC-07: 多语句注入通过 API 被拒绝
# ---------------------------------------------------------------------------
class TestSqlInjectionRejection:
    """通过 API 验证多语句注入被拒绝."""

    def test_rejects_multi_statement_injection(self, client):
        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="SELECT * FROM t; DROP TABLE t",
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 422

    def test_rejects_insert(self, client):
        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="INSERT INTO users VALUES (1, 'x')",
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# SEC-09: 审计日志写入验证
# ---------------------------------------------------------------------------
class TestAuditLog:
    """验证执行 db 断言后审计日志表有记录."""

    def test_execute_writes_audit_log(self, client, db_session):
        from app.models.audit_log import AuditLog

        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="SELECT 1 as val",
            expected_result={"field": "val", "operator": "equals", "value": 1},
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 200

        # 查询审计日志表
        logs = db_session.query(AuditLog).all()
        assert len(logs) >= 1
        log = logs[-1]
        assert log.action == "execute"
        assert log.resource_type == "db_assertion"
        assert log.resource_id == assertion["id"]
        assert log.result == "success"
        assert log.actor_name == "testadmin"

    def test_failed_sql_writes_audit_log(self, client, db_session):
        from app.models.audit_log import AuditLog

        env = _create_environment(
            client,
            db_config={"db_type": "sqlite", "database": ""},
        )
        case = _create_test_case(client)
        assertion = _create_db_assertion(
            client,
            test_case_id=case["id"],
            sql_template="DELETE FROM users",
        )

        resp = client.post(
            f"{BASE}/{assertion['id']}/test",
            params={"env_id": env["id"]},
        )
        assert resp.status_code == 422

        # 校验失败也应写入审计日志
        logs = db_session.query(AuditLog).filter_by(
            resource_id=assertion["id"], result="failed"
        ).all()
        assert len(logs) >= 1
        assert logs[0].action == "execute"
        assert "禁止" in (logs[0].error_message or "")


# ---------------------------------------------------------------------------
# SEC-09: 审计日志脱敏验证
# ---------------------------------------------------------------------------
class TestAuditLogSanitization:
    """验证审计日志中敏感字段被脱敏."""

    def test_sensitive_fields_masked(self):
        from app.services.security.audit_service import sanitize_dict

        data = {
            "username": "admin",
            "password": "secret123",
            "api_key": "abc-xyz",
            "token": "Bearer xxx",
            "nested": {"secret": "hidden", "safe": "ok"},
        }
        result = sanitize_dict(data)
        assert result["username"] == "admin"
        assert result["password"] == "****"
        assert result["api_key"] == "****"
        assert result["token"] == "****"
        assert result["nested"]["secret"] == "****"
        assert result["nested"]["safe"] == "ok"

    def test_log_sanitizer_filter(self):
        """验证日志脱敏过滤器替换敏感信息."""
        import logging
        from app.services.security.log_sanitizer import SanitizingFilter

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg='password=secret123 token=abc123 user=bob',
            args=(), exc_info=None,
        )
        f = SanitizingFilter()
        assert f.filter(record) is True
        msg = record.getMessage()
        assert "secret123" not in msg
        assert "abc123" not in msg
        assert "****" in msg
        assert "user=bob" in msg
