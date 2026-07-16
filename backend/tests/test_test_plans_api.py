"""测试计划 CRUD API 测试（TDD：先写测试）。"""
from __future__ import annotations

import pytest

import app.models  # noqa: F401  注册模型元数据
from app.models.project import Project

BASE = "/api/v1/test-plans"
CASES = "/api/v1/test-cases"
PROJECT_ID = "test-plan-project"


@pytest.fixture(autouse=True)
def _seed_test_plan_project(db_session):
    db_session.add(Project(id=PROJECT_ID, name="Test plan project"))
    db_session.commit()


def _create_plan(client, **overrides):
    payload = {
        "name": "回归计划",
        "execution_mode": "sequential",
        "project_id": PROJECT_ID,
    }
    payload.update(overrides)
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _create_case(client, title="用例"):
    resp = client.post(
        CASES,
        json={
            "title": title,
            "method": "GET",
            "url": "/x",
            "project_id": PROJECT_ID,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------
class TestCreatePlan:
    def test_create_success(self, client):
        resp = client.post(
            BASE,
            json={
                "name": "冒烟计划",
                "execution_mode": "parallel",
                "marker_filter": "smoke",
                "description": "每日冒烟",
                "project_id": PROJECT_ID,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"]
        assert data["name"] == "冒烟计划"
        assert data["execution_mode"] == "parallel"
        assert data["marker_filter"] == "smoke"
        assert data["project_id"] == PROJECT_ID
        assert data["created_by"] == "test-admin-id"
        assert data["is_active"] is True
        assert data["items"] == []

    def test_create_with_defaults(self, client):
        resp = client.post(
            BASE,
            json={"name": "p", "project_id": PROJECT_ID},
        )
        data = resp.json()["data"]
        assert data["execution_mode"] == "sequential"
        assert data["marker_filter"] is None
        assert data["environment_id"] is None

    def test_create_requires_project(self, client):
        assert client.post(BASE, json={"name": "p"}).status_code == 422


# ---------------------------------------------------------------------------
# 单个查询（含用例列表）
# ---------------------------------------------------------------------------
class TestGetPlan:
    def test_get_success(self, client):
        plan = _create_plan(client)
        resp = client.get(f"{BASE}/{plan['id']}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == plan["id"]
        assert data["items"] == []

    def test_get_not_found(self, client):
        resp = client.get(f"{BASE}/nope")
        assert resp.status_code == 404
        assert resp.json()["code"] == -1


# ---------------------------------------------------------------------------
# 列表分页
# ---------------------------------------------------------------------------
class TestListPlans:
    def test_list_pagination(self, client):
        for i in range(3):
            _create_plan(client, name=f"plan-{i}")
        resp = client.get(f"{BASE}?page=1&page_size=2")
        body = resp.json()
        assert body["total"] == 3
        assert len(body["data"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_list_default_pagination(self, client):
        _create_plan(client, name="only")
        body = client.get(BASE).json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["page_size"] == 20

    def test_list_empty(self, client):
        body = client.get(BASE).json()
        assert body["total"] == 0
        assert body["data"] == []


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------
class TestUpdatePlan:
    def test_update_success(self, client):
        plan = _create_plan(client, name="old")
        resp = client.put(
            f"{BASE}/{plan['id']}",
            json={"name": "new", "execution_mode": "stress"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "new"
        assert data["execution_mode"] == "stress"

    def test_update_not_found(self, client):
        assert client.put(f"{BASE}/nope", json={"name": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# 删除（级联删除计划项）
# ---------------------------------------------------------------------------
class TestDeletePlan:
    def test_delete_success(self, client):
        plan = _create_plan(client)
        assert client.delete(f"{BASE}/{plan['id']}").status_code == 200
        assert client.get(f"{BASE}/{plan['id']}").status_code == 404

    def test_delete_cascades_items(self, client, db_session):
        from app.models import TestPlanItem

        plan = _create_plan(client)
        case = _create_case(client)
        client.post(
            f"{BASE}/{plan['id']}/items",
            json={"test_case_id": case["id"], "order": 1},
        )
        before = (
            db_session.query(TestPlanItem)
            .filter_by(plan_id=plan["id"])
            .count()
        )
        assert before == 1

        client.delete(f"{BASE}/{plan['id']}")
        db_session.expire_all()
        after = (
            db_session.query(TestPlanItem)
            .filter_by(plan_id=plan["id"])
            .count()
        )
        assert after == 0

    def test_delete_not_found(self, client):
        assert client.delete(f"{BASE}/nope").status_code == 404


# ---------------------------------------------------------------------------
# 计划项管理：添加 / 移除用例
# ---------------------------------------------------------------------------
class TestPlanItems:
    def test_add_test_case_to_plan(self, client):
        plan = _create_plan(client)
        case = _create_case(client, "登录用例")
        resp = client.post(
            f"{BASE}/{plan['id']}/items",
            json={"test_case_id": case["id"], "order": 1},
        )
        assert resp.status_code == 200
        item = resp.json()["data"]
        assert item["test_case_id"] == case["id"]
        assert item["order"] == 1
        assert item["test_case"]["title"] == "登录用例"

        # 计划详情含该用例
        detail = client.get(f"{BASE}/{plan['id']}").json()["data"]
        assert len(detail["items"]) == 1
        assert detail["items"][0]["test_case_id"] == case["id"]

    def test_add_item_plan_not_found(self, client):
        case = _create_case(client)
        resp = client.post(
            f"{BASE}/nope/items",
            json={"test_case_id": case["id"], "order": 0},
        )
        assert resp.status_code == 404

    def test_add_item_case_not_found(self, client):
        plan = _create_plan(client)
        resp = client.post(
            f"{BASE}/{plan['id']}/items",
            json={"test_case_id": "nope", "order": 0},
        )
        assert resp.status_code == 404

    def test_add_multiple_items_ordered(self, client):
        plan = _create_plan(client)
        a = _create_case(client, "A")
        b = _create_case(client, "B")
        client.post(
            f"{BASE}/{plan['id']}/items",
            json={"test_case_id": a["id"], "order": 2},
        )
        client.post(
            f"{BASE}/{plan['id']}/items",
            json={"test_case_id": b["id"], "order": 1},
        )
        detail = client.get(f"{BASE}/{plan['id']}").json()["data"]
        assert len(detail["items"]) == 2
        # 按 order 升序
        assert detail["items"][0]["order"] == 1
        assert detail["items"][0]["test_case_id"] == b["id"]
        assert detail["items"][1]["order"] == 2
        assert detail["items"][1]["test_case_id"] == a["id"]

    def test_remove_test_case_from_plan(self, client):
        plan = _create_plan(client)
        case = _create_case(client)
        client.post(
            f"{BASE}/{plan['id']}/items",
            json={"test_case_id": case["id"], "order": 0},
        )
        resp = client.delete(f"{BASE}/{plan['id']}/items/{case['id']}")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        detail = client.get(f"{BASE}/{plan['id']}").json()["data"]
        assert len(detail["items"]) == 0

    def test_remove_item_not_found(self, client):
        plan = _create_plan(client)
        # 计划存在但未添加该用例
        resp = client.delete(f"{BASE}/{plan['id']}/items/nope")
        assert resp.status_code == 404

    def test_remove_item_plan_not_found(self, client):
        resp = client.delete(f"{BASE}/nope/items/nope")
        assert resp.status_code == 404
