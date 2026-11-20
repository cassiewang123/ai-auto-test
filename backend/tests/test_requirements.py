"""需求管理 API 测试."""

import pytest

from app.models.requirement import Requirement
from app.models.test_case import TestCase


def test_requirement_crud_and_coverage(client, db_session):
    case = TestCase(title="登录用例", method="POST", url="/login")
    db_session.add(case)
    db_session.flush()

    response = client.post(
        "/api/v1/requirements",
        json={
            "title": "用户登录功能",
            "description": "覆盖正常与异常登录",
            "priority": "P0",
            "case_ids": [case.id],
        },
    )
    assert response.status_code == 200
    created = response.json()["data"]
    assert created["title"] == "用户登录功能"
    assert created["coverage"] == 1

    req_id = created["id"]
    updated = client.put(
        f"/api/v1/requirements/{req_id}",
        json={"status": "covered", "title": "用户登录功能（已覆盖）"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "covered"

    listed = client.get("/api/v1/requirements", params={"status": "covered"})
    assert listed.json()["total"] == 1

    stats = client.get("/api/v1/requirements/stats")
    assert stats.json()["data"]["covered"] == 1
    assert stats.json()["data"]["total_cases"] == 1

    deleted = client.delete(f"/api/v1/requirements/{req_id}")
    assert deleted.status_code == 200
    assert db_session.get(Requirement, req_id) is None


def test_requirement_rejects_unknown_case(client):
    response = client.post(
        "/api/v1/requirements",
        json={"title": "无效用例", "case_ids": ["not-a-real-id"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["case_ids"] == []
