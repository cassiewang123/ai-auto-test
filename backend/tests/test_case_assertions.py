"""用例更新时断言规则的读取与整体替换."""
from __future__ import annotations

from app.models.test_case import AssertionRule
from app.models.test_case import TestCase as ApiTestCase


def _create_case(client, **overrides) -> dict:
    payload = {
        "title": "断言编辑测试",
        "method": "GET",
        "url": "http://example.com/health",
        "headers": {},
        "params": {},
        "assertions": [
            {
                "assertion_type": "status_code",
                "operator": "eq",
                "expected": "200",
                "priority": "P0",
                "order": 0,
            }
        ],
    }
    payload.update(overrides)
    response = client.post("/api/v1/test-cases", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_create_returns_assertions(client):
    case = _create_case(client)
    assertions = case["assertions"]
    assert len(assertions) == 1
    assert assertions[0]["assertion_type"] == "status_code"
    assert assertions[0]["expected"] == "200"


def test_update_replaces_assertions(client, db_session):
    case = _create_case(client)

    response = client.put(
        f"/api/v1/test-cases/{case['id']}",
        json={
            "assertions": [
                {
                    "assertion_type": "status_code",
                    "operator": "eq",
                    "expected": "200",
                    "priority": "P1",
                    "order": 0,
                },
                {
                    "assertion_type": "json_path",
                    "expression": "$.code",
                    "operator": "eq",
                    "expected": "200",
                    "priority": "P1",
                    "order": 1,
                },
                {
                    "assertion_type": "response_time",
                    "operator": "le",
                    "expected": "2.0",
                    "priority": "P2",
                    "order": 2,
                },
            ]
        },
    )
    assert response.status_code == 200, response.text
    assertions = response.json()["data"]["assertions"]
    assert len(assertions) == 3
    assert [a["assertion_type"] for a in assertions] == [
        "status_code",
        "json_path",
        "response_time",
    ]

    # 数据库里也只剩这 3 条，没有残留旧规则
    rows = (
        db_session.query(AssertionRule)
        .filter(AssertionRule.test_case_id == case["id"])
        .all()
    )
    assert len(rows) == 3


def test_update_without_assertions_keeps_them(client, db_session):
    case = _create_case(client)

    response = client.put(
        f"/api/v1/test-cases/{case['id']}",
        json={"title": "改名后仍保留断言"},
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["title"] == "改名后仍保留断言"
    assert len(body["assertions"]) == 1

    count = (
        db_session.query(AssertionRule)
        .filter(AssertionRule.test_case_id == case["id"])
        .count()
    )
    assert count == 1


def test_get_case_returns_editable_assertion_fields(client, db_session):
    case = _create_case(client)
    db_session.add(
        AssertionRule(
            test_case_id=case["id"],
            assertion_type="json_path",
            expression="$.data.total",
            operator="gt",
            expected="10",
            priority="P1",
            order=1,
        )
    )
    db_session.commit()

    response = client.get(f"/api/v1/test-cases/{case['id']}")
    assert response.status_code == 200
    assertions = response.json()["data"]["assertions"]
    json_path_rule = next(
        a for a in assertions if a["assertion_type"] == "json_path"
    )
    assert json_path_rule["expression"] == "$.data.total"
    assert json_path_rule["operator"] == "gt"
    assert json_path_rule["expected"] == "10"


def test_assertions_are_persisted_on_case_row(client, db_session):
    """断言写入后能通过 ORM 读回，确保编辑保存真正落库."""
    case = _create_case(client)
    client.put(
        f"/api/v1/test-cases/{case['id']}",
        json={
            "assertions": [
                {
                    "assertion_type": "header",
                    "expression": "Content-Type",
                    "operator": "contains",
                    "expected": "application/json",
                    "priority": "P1",
                    "order": 0,
                }
            ]
        },
    )
    db_case = db_session.get(ApiTestCase, case["id"])
    db_session.refresh(db_case)
    assert len(db_case.assertions) == 1
    assert db_case.assertions[0].assertion_type == "header"
    assert db_case.assertions[0].expression == "Content-Type"
