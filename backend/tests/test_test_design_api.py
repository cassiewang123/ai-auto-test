"""AI 测试用例生成 API 测试：会话、测试点、用例与写入用例库."""

from __future__ import annotations

import io

from app.models.functional_test_case import FunctionalTestCase
from app.models.test_case import TestCase
from app.models.test_design import GeneratedCase, GeneratedTestPoint

DESCRIPTION = (
    "用户登录功能：用户名与密码登录。密码长度 8-32 位，用户名唯一。"
    "登录页面提供用户名、密码输入框与登录按钮。"
)


def _create_requirement(client, **overrides):
    payload = {"title": "登录、项目、需求管理需求", "description": DESCRIPTION}
    payload.update(overrides)
    response = client.post("/api/v1/requirements", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_session(client, **overrides):
    payload = {"mode": "quick", "title": "登录用例生成"}
    payload.update(overrides)
    response = client.post("/api/v1/test-design/sessions", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _session_with_points(client, mode: str = "quick"):
    requirement = _create_requirement(client)
    session = _create_session(
        client, requirement_id=requirement["id"], mode=mode
    )
    client.post(f"/api/v1/test-design/sessions/{session['id']}/analyze", json={})
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-points"
    )
    assert response.status_code == 200, response.text
    return session, response.json()["data"]


def test_create_session_requires_existing_requirement(client):
    response = client.post(
        "/api/v1/test-design/sessions",
        json={"requirement_id": "not-exist"},
    )
    assert response.status_code == 404


def test_create_session_rejects_unknown_mode(client):
    response = client.post(
        "/api/v1/test-design/sessions", json={"mode": "invalid"}
    )
    assert response.status_code == 422


def test_create_session_uses_requirement_title(client):
    requirement = _create_requirement(client)
    session = _create_session(client, requirement_id=requirement["id"], title=None)
    assert session["title"] == requirement["title"]
    assert session["requirement_title"] == requirement["title"]
    assert session["status"] == "clarifying"
    assert session["review_dimensions"]


def test_list_and_delete_session(client):
    session = _create_session(client)
    listed = client.get("/api/v1/test-design/sessions")
    assert listed.json()["total"] == 1

    assert (
        client.delete(f"/api/v1/test-design/sessions/{session['id']}").status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/test-design/sessions/{session['id']}").status_code
        == 404
    )


def test_generate_points_requires_source(client):
    session = _create_session(client)
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-points"
    )
    assert response.status_code == 422
    assert "需求" in response.json()["message"]


def test_generate_points_produces_confirmable_points(client, db_session):
    session, detail = _session_with_points(client)

    assert detail["status"] == "points_ready"
    assert detail["engine"] == "rule"
    assert detail["test_points"]
    assert all(point["selected"] for point in detail["test_points"])
    assert all(point["module"] and point["point"] for point in detail["test_points"])

    stored = (
        db_session.query(GeneratedTestPoint)
        .filter_by(session_id=session["id"])
        .count()
    )
    assert stored == len(detail["test_points"])


def test_stepwise_mode_asks_questions_first(client):
    requirement = _create_requirement(client)
    session = _create_session(
        client, requirement_id=requirement["id"], mode="stepwise"
    )
    detail = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-points"
    ).json()["data"]
    kinds = [message.get("kind") for message in detail["messages"]]
    assert "questions" in kinds
    questions = [
        message for message in detail["messages"] if message.get("kind") == "questions"
    ]
    assert "需求尚不明确" in questions[0]["content"]


def test_quick_mode_does_not_ask_questions(client):
    session, detail = _session_with_points(client, mode="quick")
    kinds = [message.get("kind") for message in detail["messages"]]
    assert "questions" not in kinds


def test_generate_points_replaces_previous_points(client, db_session):
    session, first = _session_with_points(client)
    second = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-points"
    ).json()["data"]
    stored = (
        db_session.query(GeneratedTestPoint)
        .filter_by(session_id=session["id"])
        .count()
    )
    # 重新拆解应替换而不是累加
    assert stored == len(second["test_points"])


def test_update_points_edits_and_unselects(client):
    session, detail = _session_with_points(client)
    point = detail["test_points"][0]

    response = client.put(
        f"/api/v1/test-design/sessions/{session['id']}/points",
        json={
            "points": [
                {
                    "id": point["id"],
                    "module": "自定义模块",
                    "point": "人工改写后的测试点",
                    "priority": "P0",
                    "selected": False,
                }
            ]
        },
    )
    assert response.status_code == 200
    updated = {item["id"]: item for item in response.json()["data"]["test_points"]}
    assert updated[point["id"]]["module"] == "自定义模块"
    assert updated[point["id"]]["point"] == "人工改写后的测试点"
    assert updated[point["id"]]["selected"] is False


def test_update_points_ignores_foreign_ids(client):
    session, detail = _session_with_points(client)
    other_session, other_detail = _session_with_points(client)
    foreign_point = other_detail["test_points"][0]

    response = client.put(
        f"/api/v1/test-design/sessions/{session['id']}/points",
        json={"points": [{"id": foreign_point["id"], "point": "篡改"}]},
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["data"]["test_points"]]
    assert foreign_point["id"] not in ids
    # 另一个会话的数据不受影响
    other = client.get(
        f"/api/v1/test-design/sessions/{other_session['id']}"
    ).json()["data"]
    assert other["test_points"][0]["point"] == foreign_point["point"]


def test_generate_cases_requires_points(client):
    session = _create_session(client, title="空会话", prompt="随便测测")
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={}
    )
    assert response.status_code == 422
    assert "测试点" in response.json()["message"]


def test_generate_cases_from_selected_points(client, db_session):
    session, detail = _session_with_points(client)
    selected_ids = {point["id"] for point in detail["test_points"] if point["selected"]}

    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["case_count"] == len(selected_ids)
    assert data["session"]["status"] == "cases_ready"

    cases = db_session.query(GeneratedCase).filter_by(session_id=session["id"]).all()
    assert len(cases) == len(selected_ids)
    for case in cases:
        assert case.title
        assert case.steps
        assert case.expected


def test_generate_cases_skips_unselected_points(client, db_session):
    session, detail = _session_with_points(client)
    all_points = detail["test_points"]
    if len(all_points) < 2:
        return
    # 只保留第一个测试点
    client.put(
        f"/api/v1/test-design/sessions/{session['id']}/points",
        json={
            "points": [
                {"id": point["id"], "selected": index == 0}
                for index, point in enumerate(all_points)
            ]
        },
    )
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={}
    )
    assert response.json()["data"]["case_count"] == 1


def test_generate_cases_for_specific_point_ids(client):
    session, detail = _session_with_points(client)
    target = [detail["test_points"][0]["id"]]
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-cases",
        json={"point_ids": target},
    )
    assert response.status_code == 200
    assert response.json()["data"]["case_count"] == 1


def test_generate_cases_rejects_unselected_all(client):
    session, detail = _session_with_points(client)
    client.put(
        f"/api/v1/test-design/sessions/{session['id']}/points",
        json={
            "points": [
                {"id": point["id"], "selected": False}
                for point in detail["test_points"]
            ]
        },
    )
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={}
    )
    assert response.status_code == 422


def test_review_session_returns_scores(client):
    session, _ = _session_with_points(client)
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})

    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/review", json={}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["overall_score"] > 0
    assert data["dimension_scores"]
    assert isinstance(data["issues"], list)


def test_review_before_cases_returns_zero_score(client):
    session, _ = _session_with_points(client)
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/review", json={}
    )
    assert response.status_code == 200
    assert response.json()["data"]["overall_score"] == 0.0


def test_review_respects_custom_dimensions(client):
    session, _ = _session_with_points(client)
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/review",
        json={"dimensions": {"覆盖完整性": 5, "正确性": 1}},
    )
    data = response.json()["data"]
    # 参与加权计分的只有勾选的两个维度，dimension_scores 仍给出全部参考得分
    assert data["dimensions"] == {"覆盖完整性": 5, "正确性": 1}
    assert {"覆盖完整性", "正确性"} <= set(data["dimension_scores"])


def test_review_dimension_weights_are_clamped(client):
    session, _ = _session_with_points(client)
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/review",
        json={"dimensions": {"覆盖完整性": 99, "未知维度": 3}},
    )
    data = response.json()["data"]
    # 权重上限 5，未知维度被丢弃
    assert data["dimensions"] == {"覆盖完整性": 5}


def test_import_cases_writes_functional_test_cases(client, db_session):
    """AI 用例必须写入功能测试用例库，而不是 API 自动化用例表."""
    requirement = _create_requirement(client)
    session = _create_session(client, requirement_id=requirement["id"])
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-points")
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})

    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/import-cases", json={}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["created_count"] > 0

    created = (
        db_session.query(FunctionalTestCase)
        .filter_by(design_session_id=session["id"])
        .all()
    )
    assert len(created) == data["created_count"]
    for case in created:
        assert case.source == "ai"
        assert case.title
        assert case.steps  # 功能用例携带操作步骤
        assert case.expected
        assert case.requirement_id == requirement["id"]

    # 关键断言：API 自动化用例表不得被写入
    assert db_session.query(TestCase).count() == 0

    detail = client.get(f"/api/v1/test-design/sessions/{session['id']}").json()["data"]
    assert detail["status"] == "imported"
    assert len(detail["case_ids"]) == data["created_count"]
    assert all(case["imported_case_id"] for case in detail["cases"])


def test_imported_cases_visible_in_functional_case_list(client):
    requirement = _create_requirement(client)
    session = _create_session(client, requirement_id=requirement["id"])
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-points")
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})
    imported = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/import-cases", json={}
    ).json()["data"]

    listed = client.get(
        "/api/v1/functional-test-cases",
        params={"requirement_id": requirement["id"]},
    ).json()
    assert listed["total"] == imported["created_count"]
    first = listed["data"][0]
    assert first["steps"]
    assert first["source"] == "ai"

    # API 自动化用例接口不应看到这些用例
    api_cases = client.get("/api/v1/test-cases").json()
    assert api_cases["total"] == 0


def test_import_cases_links_requirement_coverage(client):
    requirement = _create_requirement(client)
    session = _create_session(client, requirement_id=requirement["id"])
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-points")
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})
    imported = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/import-cases", json={}
    ).json()["data"]

    detail = client.get(f"/api/v1/requirements/{requirement['id']}").json()["data"]
    assert detail["coverage"] == imported["created_count"]
    assert detail["status"] == "active"


def test_import_cases_without_cases_is_rejected(client):
    session = _create_session(client, title="空会话", prompt="随便测测")
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/import-cases", json={}
    )
    assert response.status_code == 422


def test_send_message_appends_conversation(client):
    session = _create_session(client, mode="stepwise")
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/messages",
        json={"message": "密码规则是 8-32 位，允许字母数字"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["messages"][0]["content"] == "密码规则是 8-32 位，允许字母数字"
    assert data["prompt"] == "密码规则是 8-32 位，允许字母数字"


def test_knowledge_base_reference_is_recorded(client):
    kb = client.post(
        "/api/v1/knowledge-bases", json={"name": "技术文档", "chunk_size": 200}
    ).json()["data"]
    client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/documents",
        files={
            "file": (
                "架构.md",
                io.BytesIO(
                    "用户登录使用 JWT 令牌，令牌有效期 2 小时，过期后需重新登录。".encode()
                ),
                "text/markdown",
            )
        },
    )
    requirement = _create_requirement(client)
    session = _create_session(
        client, requirement_id=requirement["id"], knowledge_base_id=kb["id"]
    )
    detail = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/generate-points"
    ).json()["data"]
    assert detail["knowledge_base_name"] == "技术文档"
    # 检索命中与否取决于关键词，只要不报错且字段可用即可
    assert isinstance(detail["knowledge_refs"], list)


# ---------------------------------------------------------------------------
# 可执行用例：产出形态、测试数据与接口请求落库
# ---------------------------------------------------------------------------
def test_session_stores_output_mode(client):
    manual = _create_session(client, mode="quick")
    assert manual["output_mode"] == "manual"

    api = _create_session(client, mode="quick", output_mode="api")
    assert api["output_mode"] == "api"


def test_invalid_output_mode_falls_back_to_manual(client):
    session = _create_session(client, mode="quick", output_mode="不存在的形态")
    assert session["output_mode"] == "manual"


def test_generated_cases_payload_contains_executable_fields(client):
    """用例 payload 必须带 test_data 与 executable 标记."""
    session, detail = _session_with_points(client)
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})
    detail = client.get(f"/api/v1/test-design/sessions/{session['id']}").json()["data"]
    assert detail["cases"]
    case = detail["cases"][0]
    for field in ("test_data", "request_headers", "assertions", "executable"):
        assert field in case
    # 规则引擎不产出请求定义，因此不可执行
    assert case["executable"] is False


def test_import_writes_executable_api_case(client, db_session):
    """带 method+url 的用例导入时，应同时写入接口用例库."""
    from app.models.api_case_record import ApiCaseRecord

    session, _ = _session_with_points(client)
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})

    # 直接给已生成的用例补上可执行字段（模拟 LLM 产出接口形态用例）
    case = db_session.query(GeneratedCase).filter_by(session_id=session["id"]).first()
    case.request_method = "POST"
    case.request_url = "/api/v1/import/check"
    case.request_headers = {"Content-Type": "application/json"}
    case.request_body = {"billNo": "XJ001"}
    case.assertions = [{"type": "status_code", "operator": "eq", "expected": 400}]
    case.test_data = [{"field": "分单号", "value": "XJ001", "note": "已存在"}]
    db_session.commit()

    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/import-cases", json={}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    # 只有被补齐请求定义的那一条会进接口用例库
    assert data["created_count"] >= 1
    assert len(data["api_case_ids"]) == 1

    api_case = db_session.get(ApiCaseRecord, data["api_case_ids"][0])
    assert api_case.method == "POST"
    assert api_case.url == "/api/v1/import/check"
    assert api_case.body == {"billNo": "XJ001"}
    # 异常分类映射为接口用例的 exception 场景
    assert api_case.case_type in {"normal", "exception"}

    functional = db_session.get(FunctionalTestCase, data["test_case_ids"][0])
    assert functional.test_data == [
        {"field": "分单号", "value": "XJ001", "note": "已存在"}
    ]
    assert functional.request_method == "POST"


def test_import_skips_api_case_without_request(client, db_session):
    """没有请求定义的用例（人工形态）不写接口用例库."""
    session, _ = _session_with_points(client)
    client.post(f"/api/v1/test-design/sessions/{session['id']}/generate-cases", json={})
    response = client.post(
        f"/api/v1/test-design/sessions/{session['id']}/import-cases", json={}
    )
    data = response.json()["data"]
    assert data["api_case_ids"] == []
    assert data["created_count"] >= 1
