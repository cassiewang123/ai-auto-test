"""接口分组管理 API 测试."""

from __future__ import annotations

from app.models.api_group import ApiGroup
from app.models.test_case import TestCase


def _create_case(db_session, title: str, group_path: str | None, project_id: str | None = None):
    case = TestCase(
        title=title,
        method="GET",
        url="/api/v1/probe",
        group_path=group_path,
        project_id=project_id,
    )
    db_session.add(case)
    db_session.flush()
    return case


def _create_group(client, **overrides):
    payload = {"name": "新建模块"}
    payload.update(overrides)
    response = client.post("/api/v1/api-groups", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_list_includes_derived_groups_and_parents(client, db_session):
    _create_case(db_session, "用例A", "swgd-imap-content/ApiType 码表")
    _create_case(db_session, "用例B", "swgd-imap-content/ApiService 接口调试")

    response = client.get("/api/v1/api-groups")
    assert response.status_code == 200
    data = response.json()
    paths = {item["path"] for item in data["groups"]}
    # 叶子分组与其上级模块都应出现
    assert "swgd-imap-content" in paths
    assert "swgd-imap-content/ApiType 码表" in paths
    assert "swgd-imap-content/ApiService 接口调试" in paths

    top = next(item for item in data["groups"] if item["path"] == "swgd-imap-content")
    assert top["case_count"] == 2
    assert top["derived"] is True


def test_list_counts_include_child_groups(client, db_session):
    _create_case(db_session, "用例A", "swgd-imap-content/ApiType 码表")
    _create_case(db_session, "用例B", "swgd-imap-content/ApiService 接口调试")

    data = client.get("/api/v1/api-groups").json()
    leaf = next(
        item
        for item in data["groups"]
        if item["path"] == "swgd-imap-content/ApiType 码表"
    )
    assert leaf["case_count"] == 1
    assert leaf["name"] == "ApiType 码表"
    assert leaf["parent_path"] == "swgd-imap-content"


def test_create_top_level_group(client):
    created = _create_group(client, name="磐石关务", description="主模块")
    assert created["path"] == "磐石关务"
    assert created["name"] == "磐石关务"
    assert created["parent_path"] is None
    assert created["derived"] is False
    assert created["case_count"] == 0

    listed = client.get("/api/v1/api-groups").json()
    paths = {item["path"] for item in listed["groups"]}
    assert "磐石关务" in paths


def test_create_child_group(client):
    _create_group(client, name="swgd-imap-content")
    child = _create_group(
        client, name="ApiType 码表", parent_path="swgd-imap-content"
    )
    assert child["path"] == "swgd-imap-content/ApiType 码表"
    assert child["parent_path"] == "swgd-imap-content"


def test_create_rejects_duplicate(client):
    _create_group(client, name="重复分组")
    response = client.post("/api/v1/api-groups", json={"name": "重复分组"})
    assert response.status_code == 422


def test_create_rejects_slash_in_name(client):
    response = client.post(
        "/api/v1/api-groups", json={"name": "A/B"}
    )
    assert response.status_code == 422


def test_create_rejects_unknown_parent(client):
    response = client.post(
        "/api/v1/api-groups",
        json={"name": "子分组", "parent_path": "不存在的父级"},
    )
    assert response.status_code == 404


def test_rename_group_updates_cases(client, db_session):
    group = _create_group(client, name="旧模块")
    _create_case(db_session, "用例A", "旧模块")
    _create_case(db_session, "用例B", "旧模块/子模块")
    db_session.commit()

    response = client.put(
        f"/api/v1/api-groups/{group['id']}", json={"name": "新模块"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["path"] == "新模块"

    db_session.expire_all()
    paths = {
        case.title: case.group_path
        for case in db_session.query(TestCase).all()
    }
    assert paths["用例A"] == "新模块"
    # 子分组路径按前缀同步改写
    assert paths["用例B"] == "新模块/子模块"


def test_rename_group_updates_child_group_records(client, db_session):
    parent = _create_group(client, name="父模块")
    child = _create_group(client, name="子模块", parent_path="父模块")

    client.put(f"/api/v1/api-groups/{parent['id']}", json={"name": "新父模块"})

    db_session.expire_all()
    renamed = db_session.get(ApiGroup, child["id"])
    assert renamed.path == "新父模块/子模块"
    assert renamed.parent_path == "新父模块"


def test_move_group_to_new_parent(client, db_session):
    _create_group(client, name="模块A")
    _create_group(client, name="模块B")
    group = _create_group(client, name="子模块", parent_path="模块A")
    _create_case(db_session, "用例A", "模块A/子模块")
    db_session.commit()

    response = client.put(
        f"/api/v1/api-groups/{group['id']}", json={"parent_path": "模块B"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["path"] == "模块B/子模块"

    db_session.expire_all()
    case = db_session.query(TestCase).filter_by(title="用例A").one()
    assert case.group_path == "模块B/子模块"


def test_cannot_move_group_under_itself(client):
    _create_group(client, name="父")
    child = _create_group(client, name="子", parent_path="父")

    response = client.put(
        f"/api/v1/api-groups/{child['id']}", json={"parent_path": child["path"]}
    )
    assert response.status_code == 422


def test_rename_rejects_duplicate(client):
    _create_group(client, name="分组一")
    second = _create_group(client, name="分组二")
    response = client.put(
        f"/api/v1/api-groups/{second['id']}", json={"name": "分组一"}
    )
    assert response.status_code == 422


def test_update_description_and_sort(client):
    group = _create_group(client, name="带说明分组")
    response = client.put(
        f"/api/v1/api-groups/{group['id']}",
        json={"description": "这是说明", "sort_order": 5},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["description"] == "这是说明"
    assert data["sort_order"] == 5


def test_delete_moves_cases_to_parent(client, db_session):
    _create_group(client, name="父分组")
    child = _create_group(client, name="子分组", parent_path="父分组")
    _create_case(db_session, "用例A", "父分组/子分组")
    _create_case(db_session, "用例B", "父分组/子分组/更深")
    db_session.commit()

    response = client.delete(f"/api/v1/api-groups/{child['id']}")
    assert response.status_code == 200
    assert response.json()["data"]["moved_cases"] == 2

    db_session.expire_all()
    paths = {case.title: case.group_path for case in db_session.query(TestCase).all()}
    assert paths["用例A"] == "父分组"
    assert paths["用例B"] == "父分组/更深"
    assert db_session.get(ApiGroup, child["id"]) is None


def test_delete_top_level_group_keeps_cases_without_group(client, db_session):
    group = _create_group(client, name="顶层分组")
    _create_case(db_session, "用例A", "顶层分组")
    db_session.commit()

    response = client.delete(f"/api/v1/api-groups/{group['id']}")
    assert response.status_code == 200

    db_session.expire_all()
    case = db_session.query(TestCase).filter_by(title="用例A").one()
    assert case.group_path is None


def test_update_unknown_group_returns_404(client):
    response = client.put(
        "/api/v1/api-groups/not-exist", json={"name": "新名称"}
    )
    assert response.status_code == 404


def test_groups_scoped_by_project(client, db_session):
    project_a = "11111111-1111-1111-1111-111111111111"
    _create_case(db_session, "A用例", "项目A模块", project_id=project_a)
    _create_case(db_session, "B用例", "项目B模块", project_id=None)
    db_session.commit()

    data = client.get(
        "/api/v1/api-groups", params={"project_id": project_a}
    ).json()
    paths = {item["path"] for item in data["groups"]}
    assert "项目A模块" in paths
    assert "项目B模块" not in paths
