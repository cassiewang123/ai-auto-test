"""测试用例 CRUD API 测试（TDD：先写测试）。"""
from __future__ import annotations

import app.models  # noqa: F401  注册模型元数据

BASE = "/api/v1/test-cases"


def _create_case(client, **overrides):
    payload = {
        "title": "用户登录",
        "method": "POST",
        "url": "/api/login",
        "headers": {"Content-Type": "application/json"},
        "params": {"redirect": "1"},
        "body": {"username": "test", "password": "123"},
        "markers": ["smoke", "api"],
        "group_path": "用户管理/认证",
        "extract_rules": [
            {"name": "token", "source": "body", "expression": "$.token"}
        ],
        "assertions": [
            {
                "assertion_type": "status_code",
                "operator": "eq",
                "expected": "200",
            },
            {
                "assertion_type": "json_path",
                "expression": "$.code",
                "operator": "eq",
                "expected": "0",
            },
        ],
    }
    payload.update(overrides)
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# 创建（含断言规则级联）
# ---------------------------------------------------------------------------
class TestCreateTestCase:
    def test_create_with_assertions(self, client):
        case = _create_case(client)
        assert case["id"]
        assert case["title"] == "用户登录"
        assert case["method"] == "POST"
        assert case["url"] == "/api/login"
        assert case["headers"] == {"Content-Type": "application/json"}
        assert case["markers"] == ["smoke", "api"]
        assert case["group_path"] == "用户管理/认证"
        assert len(case["extract_rules"]) == 1
        # 断言规则级联创建
        assert len(case["assertions"]) == 2
        for a in case["assertions"]:
            assert a["id"]
            assert a["test_case_id"] == case["id"]
        types = [a["assertion_type"] for a in case["assertions"]]
        assert "status_code" in types
        assert "json_path" in types

    def test_create_with_defaults(self, client):
        resp = client.post(
            BASE, json={"title": "简单用例", "method": "GET", "url": "/ping"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["headers"] == {}
        assert data["params"] == {}
        assert data["body"] is None
        assert data["markers"] == []
        assert data["assertions"] == []
        assert data["extract_rules"] == []
        assert data["is_active"] is True

    def test_create_accepts_json_array_body(self, client):
        case = _create_case(
            client,
            title="批量创建用户",
            body=[{"username": "alice"}, {"username": "bob"}],
        )

        assert case["body"] == [{"username": "alice"}, {"username": "bob"}]

    def test_create_assertion_defaults(self, client):
        """断言规则字段缺省时使用默认值。"""
        resp = client.post(
            BASE,
            json={
                "title": "t",
                "method": "GET",
                "url": "/x",
                "assertions": [{"assertion_type": "status_code"}],
            },
        )
        a = resp.json()["data"]["assertions"][0]
        assert a["operator"] == "eq"
        assert a["priority"] == "P1"
        assert a["order"] == 0


# ---------------------------------------------------------------------------
# 单个查询
# ---------------------------------------------------------------------------
class TestGetTestCase:
    def test_get_success(self, client):
        case = _create_case(client)
        resp = client.get(f"{BASE}/{case['id']}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == case["id"]
        assert len(data["assertions"]) == 2

    def test_get_not_found(self, client):
        resp = client.get(f"{BASE}/nope")
        assert resp.status_code == 404
        assert resp.json()["code"] == -1


# ---------------------------------------------------------------------------
# 列表分页 + 筛选
# ---------------------------------------------------------------------------
class TestListTestCases:
    def test_list_pagination(self, client):
        for i in range(3):
            _create_case(client, title=f"case-{i}")
        resp = client.get(f"{BASE}?page=1&page_size=2")
        body = resp.json()
        assert body["total"] == 3
        assert len(body["data"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_list_default_pagination(self, client):
        _create_case(client, title="only")
        body = client.get(BASE).json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["page_size"] == 20

    def test_list_filter_by_group_path(self, client):
        _create_case(client, group_path="模块A")
        _create_case(client, group_path="模块B")
        _create_case(client, group_path="模块A/子")
        resp = client.get(f"{BASE}?group_path=模块A")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["group_path"] == "模块A"

    def test_list_filter_by_markers(self, client):
        _create_case(client, markers=["smoke"])
        _create_case(client, markers=["regression"])
        _create_case(client, markers=["smoke", "api"])
        resp = client.get(f"{BASE}?marker=smoke")
        body = resp.json()
        assert body["total"] == 2
        for c in body["data"]:
            assert "smoke" in c["markers"]

    def test_list_empty(self, client):
        body = client.get(BASE).json()
        assert body["total"] == 0
        assert body["data"] == []


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------
class TestUpdateTestCase:
    def test_update_success(self, client):
        case = _create_case(client)
        resp = client.put(
            f"{BASE}/{case['id']}",
            json={"title": "新标题", "method": "PUT"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "新标题"
        assert data["method"] == "PUT"
        # 未更新字段保留
        assert data["url"] == "/api/login"
        assert len(data["assertions"]) == 2

    def test_update_not_found(self, client):
        resp = client.put(f"{BASE}/nope", json={"title": "x"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 删除（级联删除断言规则）
# ---------------------------------------------------------------------------
class TestDeleteTestCase:
    def test_delete_success(self, client):
        case = _create_case(client)
        resp = client.delete(f"{BASE}/{case['id']}")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert client.get(f"{BASE}/{case['id']}").status_code == 404

    def test_delete_cascades_assertions(self, client, db_session):
        from app.models import AssertionRule

        case = _create_case(client)
        cid = case["id"]
        before = (
            db_session.query(AssertionRule)
            .filter_by(test_case_id=cid)
            .count()
        )
        assert before == 2

        client.delete(f"{BASE}/{cid}")

        db_session.expire_all()
        after = (
            db_session.query(AssertionRule)
            .filter_by(test_case_id=cid)
            .count()
        )
        assert after == 0

    def test_delete_not_found(self, client):
        assert client.delete(f"{BASE}/nope").status_code == 404


# ---------------------------------------------------------------------------
# 复制用例
# ---------------------------------------------------------------------------
class TestCopyTestCase:
    def test_copy_success(self, client):
        case = _create_case(client)
        resp = client.post(f"{BASE}/{case['id']}/copy")
        assert resp.status_code == 200
        new = resp.json()["data"]
        assert new["id"] != case["id"]
        assert new["title"] == "用户登录 (副本)"
        # 请求定义被复制
        assert new["method"] == case["method"]
        assert new["url"] == case["url"]
        assert new["markers"] == case["markers"]
        assert new["group_path"] == case["group_path"]
        assert new["extract_rules"] == case["extract_rules"]
        # 断言规则也被复制，且 id 不同
        assert len(new["assertions"]) == 2
        new_ids = {a["id"] for a in new["assertions"]}
        old_ids = {a["id"] for a in case["assertions"]}
        assert new_ids.isdisjoint(old_ids)
        for a in new["assertions"]:
            assert a["test_case_id"] == new["id"]

    def test_copy_not_found(self, client):
        resp = client.post(f"{BASE}/nope/copy")
        assert resp.status_code == 404


class TestDeleteCaseWithExecutionHistory:
    """有执行历史的用例必须可删除（回归：删除接口曾返回 500）."""

    def test_delete_case_with_test_results(self, client, db_session):
        import uuid

        from app.models.test_case import TestCase
        from app.models.test_result import TestResult

        case = _create_case(client)
        db_session.add(
            TestResult(
                run_id=str(uuid.uuid4()),
                test_case_id=case["id"],
                status="passed",
            )
        )
        db_session.commit()

        resp = client.delete(f"{BASE}/{case['id']}")
        assert resp.status_code == 200, resp.text
        assert db_session.get(TestCase, case["id"]) is None
        assert (
            db_session.query(TestResult)
            .filter_by(test_case_id=case["id"])
            .count()
            == 0
        )

    def test_batch_delete_cases_with_test_results(self, client, db_session):
        import uuid

        from app.models.test_case import TestCase
        from app.models.test_result import TestResult

        first = _create_case(client, title="批量删除一")
        second = _create_case(client, title="批量删除二")
        for case in (first, second):
            db_session.add(
                TestResult(
                    run_id=str(uuid.uuid4()),
                    test_case_id=case["id"],
                    status="failed",
                )
            )
        db_session.commit()

        resp = client.post(
            f"{BASE}/batch-delete",
            json={"case_ids": [first["id"], second["id"]]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["deleted"] == 2
        assert db_session.query(TestResult).count() == 0
        assert db_session.get(TestCase, first["id"]) is None


def test_delete_case_with_fk_enforced():
    """在开启外键约束的库上验证删除不再抛 IntegrityError."""
    import uuid

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.api.v1.test_cases import _delete_case_dependents
    from app.database import Base
    from app.models.test_case import TestCase
    from app.models.test_result import TestResult

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(conn, _record):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        case = TestCase(title="带历史", method="GET", url="/x")
        session.add(case)
        session.flush()
        session.add(
            TestResult(
                run_id=str(uuid.uuid4()),
                test_case_id=case.id,
                status="passed",
            )
        )
        session.commit()

        _delete_case_dependents(session, [case.id])
        session.delete(case)
        session.commit()
        assert session.get(TestCase, case.id) is None
    finally:
        session.close()
        engine.dispose()
