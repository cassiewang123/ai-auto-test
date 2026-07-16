"""环境管理 CRUD API 测试（TDD：先写测试）。"""
from __future__ import annotations

# 确保所有 ORM 模型在测试收集阶段注册到 Base.metadata，
# 这样 conftest 的 db_engine fixture 执行 create_all 时能建表。
import app.models  # noqa: F401

BASE = "/api/v1/environments"


def _create_env(client, **overrides):
    payload = {
        "name": "生产环境",
        "base_url": "https://api.example.com",
        "variables": {"token": "abc123"},
        "description": "线上生产环境",
    }
    payload.update(overrides)
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------
class TestCreateEnvironment:
    def test_create_success(self, client):
        payload = {
            "name": "测试环境",
            "base_url": "https://test.example.com",
            "variables": {"token": "t1", "db": "sqlite"},
            "description": "用于测试",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["message"] == "ok"
        data = body["data"]
        assert data["id"]
        assert data["name"] == "测试环境"
        assert data["base_url"] == "https://test.example.com"
        assert data["variables"] == {"token": "t1", "db": "sqlite"}
        assert data["description"] == "用于测试"
        assert data["is_active"] is True

    def test_create_with_defaults(self, client):
        """variables/description 缺省时使用默认值。"""
        resp = client.post(
            BASE, json={"name": "dev", "base_url": "https://dev.example.com"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["variables"] == {}
        assert data["description"] is None


# ---------------------------------------------------------------------------
# 单个查询
# ---------------------------------------------------------------------------
class TestGetEnvironment:
    def test_get_success(self, client):
        env = _create_env(client, name="staging")
        resp = client.get(f"{BASE}/{env['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["id"] == env["id"]
        assert body["data"]["name"] == "staging"

    def test_get_not_found(self, client):
        resp = client.get(f"{BASE}/nonexistent-id")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == -1


# ---------------------------------------------------------------------------
# 列表分页 + 搜索
# ---------------------------------------------------------------------------
class TestListEnvironments:
    def test_list_pagination(self, client):
        for i in range(3):
            _create_env(client, name=f"env-{i}")
        resp = client.get(f"{BASE}?page=1&page_size=2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["total"] == 3
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert len(body["data"]) == 2

        # 第二页
        resp2 = client.get(f"{BASE}?page=2&page_size=2")
        assert resp2.json()["total"] == 3
        assert len(resp2.json()["data"]) == 1

    def test_list_default_pagination(self, client):
        _create_env(client, name="only")
        resp = client.get(BASE)
        body = resp.json()
        assert body["page"] == 1
        assert body["page_size"] == 20
        assert body["total"] == 1

    def test_list_search_by_name(self, client):
        _create_env(client, name="dev-env")
        _create_env(client, name="staging-env")
        _create_env(client, name="prod")
        resp = client.get(f"{BASE}?name=env")
        body = resp.json()
        assert body["total"] == 2
        names = [e["name"] for e in body["data"]]
        assert "dev-env" in names
        assert "staging-env" in names
        assert "prod" not in names

    def test_list_empty(self, client):
        resp = client.get(BASE)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["data"] == []


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------
class TestUpdateEnvironment:
    def test_update_success(self, client):
        env = _create_env(client, name="old")
        resp = client.put(
            f"{BASE}/{env['id']}",
            json={"name": "new", "base_url": "https://new.example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "new"
        assert data["base_url"] == "https://new.example.com"
        # 未更新字段保留
        assert data["description"] == "线上生产环境"

    def test_update_not_found(self, client):
        resp = client.put(f"{BASE}/nope", json={"name": "x"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------
class TestDeleteEnvironment:
    def test_delete_success(self, client):
        env = _create_env(client, name="to-delete")
        resp = client.delete(f"{BASE}/{env['id']}")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        # 删除后查询应 404
        resp2 = client.get(f"{BASE}/{env['id']}")
        assert resp2.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete(f"{BASE}/nope")
        assert resp.status_code == 404
