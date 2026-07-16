"""认证与权限控制模块测试（JWT + RBAC）.

覆盖：注册、登录、获取当前用户、密码错误、权限检查、角色 CRUD、
JWT 令牌过期/无效、用户管理 CRUD、角色分配。
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

# 确保模型注册到 Base.metadata（独立于 models/__init__.py 是否已集成），
# 这样 conftest 的 db_engine fixture 执行 create_all 时能建表。
import app.models.role  # noqa: F401
import app.models.user  # noqa: F401
from app.core.security import create_access_token
from app.database import get_db

BASE_AUTH = "/api/v1/auth"
BASE_USERS = "/api/v1/users"
BASE_ROLES = "/api/v1/roles"


@pytest.fixture(scope="function")
def client(db_session):
    """覆盖 conftest 的 client：在集成前手动注册 auth/users/roles 路由。

    通过检查 app.state.registered_routers 判断主 agent 是否已注册路由，
    避免集成后重复注册。
    """
    from app.api.v1 import auth, roles, users
    from app.main import create_app

    app = create_app()
    registered = getattr(app.state, "registered_routers", [])
    if "app.api.v1.auth" not in registered:
        app.include_router(auth.router, prefix="/api/v1/auth")
    if "app.api.v1.users" not in registered:
        app.include_router(users.router, prefix="/api/v1/users")
    if "app.api.v1.roles" not in registered:
        app.include_router(roles.router, prefix="/api/v1/roles")

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _register(
    client, username="admin", email="admin@test.com", password="pass123"
):
    resp = client.post(
        f"{BASE_AUTH}/register",
        json={"username": username, "email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _login(client, username="admin", password="pass123"):
    resp = client.post(
        f"{BASE_AUTH}/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_admin(client):
    """注册首个用户（超级管理员）并登录，返回 (user_data, token)。"""
    user = _register(client)
    data = _login(client)
    return user, data["access_token"]


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
class TestRegister:
    def test_first_user_becomes_superuser(self, client):
        data = _register(client, username="first", email="first@test.com")
        assert data["is_superuser"] is True
        assert data["username"] == "first"
        assert data["is_active"] is True

    def test_second_user_not_superuser(self, client):
        _register(client, username="first", email="first@test.com")
        data = _register(
            client, username="second", email="second@test.com"
        )
        assert data["is_superuser"] is False

    def test_duplicate_username(self, client):
        _register(client, username="dup", email="dup@test.com")
        resp = client.post(
            f"{BASE_AUTH}/register",
            json={"username": "dup", "email": "other@test.com", "password": "x"},
        )
        assert resp.status_code == 422

    def test_duplicate_email(self, client):
        _register(client, username="u1", email="same@test.com")
        resp = client.post(
            f"{BASE_AUTH}/register",
            json={"username": "u2", "email": "same@test.com", "password": "x"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------
class TestLogin:
    def test_login_success(self, client):
        _register(client, username="alice", email="alice@test.com", password="secret")
        data = _login(client, "alice", "secret")
        assert data["access_token"]
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "alice"

    def test_login_wrong_password(self, client):
        _register(client, username="bob", email="bob@test.com", password="right")
        resp = client.post(
            f"{BASE_AUTH}/login",
            json={"username": "bob", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post(
            f"{BASE_AUTH}/login",
            json={"username": "ghost", "password": "x"},
        )
        assert resp.status_code == 401

    def test_login_disabled_user(self, client):
        _, token = _setup_admin(client)
        u = client.post(
            BASE_USERS,
            json={"username": "dis", "email": "dis@test.com", "password": "pw"},
            headers=_auth_header(token),
        ).json()["data"]
        client.put(
            f"{BASE_USERS}/{u['id']}",
            json={"is_active": False},
            headers=_auth_header(token),
        )
        resp = client.post(
            f"{BASE_AUTH}/login",
            json={"username": "dis", "password": "pw"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 获取当前用户
# ---------------------------------------------------------------------------
class TestMe:
    def test_me_with_valid_token(self, client):
        _setup_admin(client)
        data = _login(client)
        resp = client.get(
            f"{BASE_AUTH}/me", headers=_auth_header(data["access_token"])
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "admin"

    def test_me_without_token(self, client):
        resp = client.get(f"{BASE_AUTH}/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self, client):
        resp = client.get(
            f"{BASE_AUTH}/me", headers=_auth_header("not.a.valid.token")
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 权限检查
# ---------------------------------------------------------------------------
class TestPermission:
    def test_normal_user_denied_admin_route(self, client):
        _register(client, username="admin", email="admin@test.com", password="pw")
        _register(
            client, username="normal", email="normal@test.com", password="pw"
        )
        token = _login(client, "normal", "pw")["access_token"]
        # 普通用户无 user:manage 权限
        resp = client.get(BASE_USERS, headers=_auth_header(token))
        assert resp.status_code == 403

    def test_superuser_allowed_admin_route(self, client):
        _setup_admin(client)
        token = _login(client)["access_token"]
        resp = client.get(BASE_USERS, headers=_auth_header(token))
        assert resp.status_code == 200

    def test_user_with_permission_allowed(self, client):
        _, admin_token = _setup_admin(client)
        # 创建带 user:manage 权限的角色
        role = client.post(
            BASE_ROLES,
            json={"name": "user-admin", "permissions": ["user:manage"]},
            headers=_auth_header(admin_token),
        ).json()["data"]
        # 创建普通用户
        normal = _register(
            client, username="normal", email="normal@test.com", password="pw"
        )
        # 分配角色
        resp = client.post(
            f"{BASE_USERS}/{normal['id']}/roles",
            json={"role_ids": [role["id"]]},
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 200
        # 普通用户现在应能访问 /users
        token = _login(client, "normal", "pw")["access_token"]
        resp = client.get(BASE_USERS, headers=_auth_header(token))
        assert resp.status_code == 200

    def test_normal_user_denied_role_manage(self, client):
        _, admin_token = _setup_admin(client)
        normal = _register(
            client, username="normal", email="normal@test.com", password="pw"
        )
        token = _login(client, "normal", "pw")["access_token"]
        # 普通用户不能创建角色
        resp = client.post(
            BASE_ROLES,
            json={"name": "r"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 角色 CRUD
# ---------------------------------------------------------------------------
class TestRoleCRUD:
    def test_create_role(self, client):
        _, token = _setup_admin(client)
        resp = client.post(
            BASE_ROLES,
            json={"name": "tester", "permissions": ["testcase:read"]},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "tester"
        assert data["permissions"] == ["testcase:read"]
        assert data["is_active"] is True

    def test_list_roles(self, client):
        _, token = _setup_admin(client)
        client.post(
            BASE_ROLES, json={"name": "r1"}, headers=_auth_header(token)
        )
        client.post(
            BASE_ROLES, json={"name": "r2"}, headers=_auth_header(token)
        )
        resp = client.get(BASE_ROLES, headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_update_role(self, client):
        _, token = _setup_admin(client)
        role = client.post(
            BASE_ROLES, json={"name": "r1"}, headers=_auth_header(token)
        ).json()["data"]
        resp = client.put(
            f"{BASE_ROLES}/{role['id']}",
            json={"description": "updated desc", "permissions": ["x:read"]},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["description"] == "updated desc"
        assert data["permissions"] == ["x:read"]

    def test_delete_role(self, client):
        _, token = _setup_admin(client)
        role = client.post(
            BASE_ROLES, json={"name": "r1"}, headers=_auth_header(token)
        ).json()["data"]
        resp = client.delete(
            f"{BASE_ROLES}/{role['id']}", headers=_auth_header(token)
        )
        assert resp.status_code == 200
        # 删除后查询应 404
        resp2 = client.get(
            f"{BASE_ROLES}/{role['id']}", headers=_auth_header(token)
        )
        assert resp2.status_code == 404

    def test_duplicate_role_name(self, client):
        _, token = _setup_admin(client)
        client.post(
            BASE_ROLES, json={"name": "dup"}, headers=_auth_header(token)
        )
        resp = client.post(
            BASE_ROLES, json={"name": "dup"}, headers=_auth_header(token)
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# JWT 令牌过期/无效
# ---------------------------------------------------------------------------
class TestTokenValidity:
    def test_expired_token(self, client):
        user = _register(
            client, username="exp", email="exp@test.com", password="pw"
        )
        # 构造一个已过期的令牌
        expired = create_access_token(
            {
                "sub": user["id"],
                "username": "exp",
                "is_superuser": False,
            },
            expires_delta=timedelta(seconds=-60),
        )
        resp = client.get(f"{BASE_AUTH}/me", headers=_auth_header(expired))
        assert resp.status_code == 401

    def test_token_with_nonexistent_user(self, client):
        # 令牌合法但用户不存在
        token = create_access_token(
            {
                "sub": "nonexistent-user-id",
                "username": "ghost",
                "is_superuser": False,
            }
        )
        resp = client.get(f"{BASE_AUTH}/me", headers=_auth_header(token))
        assert resp.status_code == 401

    def test_malformed_token(self, client):
        resp = client.get(
            f"{BASE_AUTH}/me", headers=_auth_header("garbage")
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 用户管理 CRUD
# ---------------------------------------------------------------------------
class TestUserManagement:
    def test_admin_create_user(self, client):
        _, token = _setup_admin(client)
        resp = client.post(
            BASE_USERS,
            json={
                "username": "newuser",
                "email": "new@test.com",
                "password": "pw",
            },
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["username"] == "newuser"
        assert data["is_superuser"] is False

    def test_admin_list_users(self, client):
        _, token = _setup_admin(client)
        client.post(
            BASE_USERS,
            json={"username": "u1", "email": "u1@test.com", "password": "pw"},
            headers=_auth_header(token),
        )
        resp = client.get(BASE_USERS, headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_admin_update_user(self, client):
        _, token = _setup_admin(client)
        u = client.post(
            BASE_USERS,
            json={"username": "u1", "email": "u1@test.com", "password": "pw"},
            headers=_auth_header(token),
        ).json()["data"]
        resp = client.put(
            f"{BASE_USERS}/{u['id']}",
            json={"email": "updated@test.com"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "updated@test.com"

    def test_admin_update_user_password(self, client):
        _, token = _setup_admin(client)
        u = client.post(
            BASE_USERS,
            json={"username": "u1", "email": "u1@test.com", "password": "pw"},
            headers=_auth_header(token),
        ).json()["data"]
        client.put(
            f"{BASE_USERS}/{u['id']}",
            json={"password": "newpw"},
            headers=_auth_header(token),
        )
        # 用新密码登录
        resp = client.post(
            f"{BASE_AUTH}/login",
            json={"username": "u1", "password": "newpw"},
        )
        assert resp.status_code == 200

    def test_admin_delete_user(self, client):
        _, token = _setup_admin(client)
        u = client.post(
            BASE_USERS,
            json={"username": "del", "email": "del@test.com", "password": "pw"},
            headers=_auth_header(token),
        ).json()["data"]
        resp = client.delete(
            f"{BASE_USERS}/{u['id']}", headers=_auth_header(token)
        )
        assert resp.status_code == 200

    def test_assign_roles_to_user(self, client):
        _, token = _setup_admin(client)
        u = client.post(
            BASE_USERS,
            json={"username": "u1", "email": "u1@test.com", "password": "pw"},
            headers=_auth_header(token),
        ).json()["data"]
        r = client.post(
            BASE_ROLES,
            json={"name": "tester", "permissions": ["testcase:read"]},
            headers=_auth_header(token),
        ).json()["data"]
        resp = client.post(
            f"{BASE_USERS}/{u['id']}/roles",
            json={"role_ids": [r["id"]]},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        roles = resp.json()["data"]["roles"]
        assert len(roles) == 1
        assert roles[0]["name"] == "tester"

    def test_assign_nonexistent_role(self, client):
        _, token = _setup_admin(client)
        u = client.post(
            BASE_USERS,
            json={"username": "u1", "email": "u1@test.com", "password": "pw"},
            headers=_auth_header(token),
        ).json()["data"]
        resp = client.post(
            f"{BASE_USERS}/{u['id']}/roles",
            json={"role_ids": ["nonexistent-role-id"]},
            headers=_auth_header(token),
        )
        assert resp.status_code == 422
