"""功能测试用例库 API 测试."""

from __future__ import annotations

from app.models.functional_test_case import (
    FunctionalCaseExecution,
    FunctionalTestCase,
)


def _create_case(client, **overrides):
    payload = {
        "title": "正常登录成功",
        "module": "登录与认证",
        "category": "功能",
        "priority": "P0",
        "preconditions": "已注册账号",
        "steps": ["打开登录页", "输入账号密码", "点击登录"],
        "expected": "登录成功并跳转首页",
        "trace_source": "用户名密码登录",
    }
    payload.update(overrides)
    response = client.post("/api/v1/functional-test-cases", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_create_and_get_functional_case(client):
    created = _create_case(client)
    assert created["title"] == "正常登录成功"
    assert created["source"] == "manual"
    assert created["status"] == "active"
    assert created["steps"] == ["打开登录页", "输入账号密码", "点击登录"]

    detail = client.get(f"/api/v1/functional-test-cases/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["module"] == "登录与认证"


def test_list_filters_by_module_and_priority(client):
    _create_case(client, title="用例A", module="登录与认证", priority="P0")
    _create_case(client, title="用例B", module="项目管理", priority="P2")

    listed = client.get(
        "/api/v1/functional-test-cases", params={"module": "登录与认证"}
    )
    assert listed.json()["total"] == 1
    assert listed.json()["data"][0]["title"] == "用例A"

    p0 = client.get("/api/v1/functional-test-cases", params={"priority": "P0"})
    assert p0.json()["total"] == 1


def test_update_and_delete_functional_case(client, db_session):
    created = _create_case(client)
    updated = client.put(
        f"/api/v1/functional-test-cases/{created['id']}",
        json={"title": "改名后的用例", "priority": "P2", "status": "draft"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "改名后的用例"
    assert updated.json()["data"]["status"] == "draft"

    deleted = client.delete(f"/api/v1/functional-test-cases/{created['id']}")
    assert deleted.status_code == 200
    assert db_session.get(FunctionalTestCase, created["id"]) is None


def test_reject_invalid_priority_and_status(client):
    bad_priority = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "非法优先级", "priority": "P9"},
    )
    assert bad_priority.status_code == 422

    bad_status = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "非法状态", "status": "unknown"},
    )
    assert bad_status.status_code == 422


def test_reject_invalid_category(client):
    response = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "非法分类", "category": "不存在"},
    )
    assert response.status_code == 422


def test_reject_unknown_requirement(client):
    response = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "挂到不存在需求", "requirement_id": "not-exist"},
    )
    assert response.status_code == 404


def test_stats_reflects_cases(client):
    _create_case(client, title="用例1", priority="P0")
    _create_case(client, title="用例2", priority="P1", status="draft")
    _create_case(client, title="用例3", priority="P2", status="deprecated")

    stats = client.get("/api/v1/functional-test-cases/stats").json()["data"]
    assert stats["total"] == 3
    assert stats["p0"] == 1
    assert stats["draft"] == 1
    assert stats["deprecated"] == 1


def test_execution_records_and_last_result(client, db_session):
    created = _create_case(client)
    url = f"/api/v1/functional-test-cases/{created['id']}/executions"

    response = client.post(
        url,
        json={
            "result": "passed",
            "actual": "跳转到首页",
            "remark": "第一轮回归",
            "run_label": "round-1",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["result"] == "passed"

    client.post(url, json={"result": "failed", "actual": "提示密码错误"})

    history = client.get(url).json()["data"]
    assert len(history) == 2

    detail = client.get(f"/api/v1/functional-test-cases/{created['id']}").json()["data"]
    # 最近一次执行结果回填到用例上
    assert detail["last_result"] == "failed"
    assert detail["last_executed_at"] is not None


def test_reject_invalid_execution_result(client):
    created = _create_case(client)
    response = client.post(
        f"/api/v1/functional-test-cases/{created['id']}/executions",
        json={"result": "unknown-result"},
    )
    assert response.status_code == 422


def test_delete_case_cascades_executions(client, db_session):
    created = _create_case(client)
    client.post(
        f"/api/v1/functional-test-cases/{created['id']}/executions",
        json={"result": "passed"},
    )
    client.delete(f"/api/v1/functional-test-cases/{created['id']}")
    assert (
        db_session.query(FunctionalCaseExecution)
        .filter_by(case_id=created["id"])
        .count()
        == 0
    )


def test_requirement_case_ids_follow_functional_cases(client, db_session):
    """功能用例关联需求后，需求的 case_ids 应同步，供覆盖率统计."""
    requirement = client.post(
        "/api/v1/requirements",
        json={"title": "登录需求", "description": "登录功能"},
    ).json()["data"]
    req_id = requirement["id"]

    case = _create_case(client, requirement_id=req_id)
    detail = client.get(f"/api/v1/requirements/{req_id}").json()["data"]
    assert case["id"] in detail["case_ids"]
    assert detail["coverage"] == 1

    # 删除功能用例后需求关联同步移除
    client.delete(f"/api/v1/functional-test-cases/{case['id']}")
    detail = client.get(f"/api/v1/requirements/{req_id}").json()["data"]
    assert case["id"] not in detail["case_ids"]
    assert detail["coverage"] == 0
