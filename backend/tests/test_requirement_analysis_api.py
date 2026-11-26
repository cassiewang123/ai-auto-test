"""需求文档上传与需求分析 API 测试."""

from __future__ import annotations

import io

from app.models.requirement_document import RequirementAnalysis


def _create_requirement(client, **overrides):
    payload = {
        "title": "登录、项目、需求管理需求",
        "description": (
            "用户登录功能：用户名与密码登录。密码长度 8-32 位，用户名唯一。"
            "登录页面提供用户名、密码输入框与登录按钮。等等一些细节后续补充。"
        ),
        "priority": "P0",
    }
    payload.update(overrides)
    response = client.post("/api/v1/requirements", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _upload(client, requirement_id, filename="需求.md", content=None):
    data = content if content is not None else (
        "# 需求补充\n\n验证码 4 位，有效期 60 秒。\n\n项目创建后自动成为项目管理员。"
    ).encode()
    return client.post(
        f"/api/v1/requirements/{requirement_id}/documents",
        files={"file": (filename, io.BytesIO(data), "text/markdown")},
    )


def test_upload_and_list_requirement_documents(client):
    requirement = _create_requirement(client)
    response = _upload(client, requirement["id"])
    assert response.status_code == 200, response.text
    document = response.json()["data"]
    assert document["filename"] == "需求.md"
    assert document["char_count"] > 0
    assert document["warnings"] == []

    listed = client.get(f"/api/v1/requirements/{requirement['id']}/documents")
    assert len(listed.json()["data"]) == 1


def test_upload_requirement_document_rejects_bad_type(client):
    requirement = _create_requirement(client)
    # .xls 现已支持（返回告警而非拒绝），这里改用确实不支持的扩展名
    response = _upload(client, requirement["id"], filename="需求.exe", content=b"bin")
    assert response.status_code == 422


def test_upload_document_to_unknown_requirement_returns_404(client):
    response = _upload(client, "not-exist")
    assert response.status_code == 404


def test_delete_requirement_document(client):
    requirement = _create_requirement(client)
    document = _upload(client, requirement["id"]).json()["data"]
    response = client.delete(
        f"/api/v1/requirements/{requirement['id']}/documents/{document['id']}"
    )
    assert response.status_code == 200
    listed = client.get(f"/api/v1/requirements/{requirement['id']}/documents")
    assert listed.json()["data"] == []


def test_analyze_requirement_outputs_three_sections(client):
    requirement = _create_requirement(client)
    _upload(client, requirement["id"])

    response = client.post(f"/api/v1/requirements/{requirement['id']}/analyze", json={})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["engine"] == "rule"
    assert data["function_items"]
    assert data["clarifications"]
    assert data["markdown"]
    assert "## 一、功能清单" in data["markdown"]
    # 附件正文也参与分析：验证码规则应出现在功能清单里
    points_text = " ".join(
        point
        for item in data["function_items"]
        for point in item.get("points", [])
    )
    assert "验证码" in points_text


def test_analyze_without_content_is_rejected(client):
    requirement = _create_requirement(
        client, title="空需求", description=None
    )
    response = client.post(f"/api/v1/requirements/{requirement['id']}/analyze", json={})
    assert response.status_code == 422
    assert "正文" in response.json()["message"]


def test_analyze_with_question_records_conversation(client):
    requirement = _create_requirement(client)
    response = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze",
        json={"question": "请补充异常场景"},
    )
    data = response.json()["data"]
    roles = [message["role"] for message in data["messages"]]
    assert roles == ["user", "assistant"]
    assert data["messages"][0]["content"] == "请补充异常场景"


def test_analyze_with_unknown_knowledge_base_returns_404(client):
    requirement = _create_requirement(client)
    response = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze",
        json={"knowledge_base_id": "not-exist"},
    )
    assert response.status_code == 404


def test_analyze_with_knowledge_base_succeeds(client):
    requirement = _create_requirement(client)
    kb = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "技术文档", "chunk_size": 200},
    ).json()["data"]
    client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/documents",
        files={
            "file": (
                "架构.md",
                io.BytesIO("用户登录使用 JWT 令牌，令牌有效期 2 小时。".encode()),
                "text/markdown",
            )
        },
    )

    response = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze",
        json={"knowledge_base_id": kb["id"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["knowledge_base_id"] == kb["id"]


def test_list_and_get_analysis_history(client):
    requirement = _create_requirement(client)
    first = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze", json={}
    ).json()["data"]
    client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze", json={}
    )

    listed = client.get(f"/api/v1/requirements/{requirement['id']}/analyses")
    assert len(listed.json()["data"]) == 2

    detail = client.get(f"/api/v1/requirements/analyses/{first['id']}")
    assert detail.json()["data"]["id"] == first["id"]


def test_continue_analysis_appends_messages(client, db_session):
    requirement = _create_requirement(client)
    analysis = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze", json={}
    ).json()["data"]

    response = client.post(
        f"/api/v1/requirements/analyses/{analysis['id']}/messages",
        json={"message": "把功能清单按模块重新梳理"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["messages"]) == 3
    assert data["messages"][-2]["content"] == "把功能清单按模块重新梳理"

    stored = db_session.get(RequirementAnalysis, analysis["id"])
    assert len(stored.messages) == 3
    # 同一行被更新而不是新增，历史链条保持单一
    assert db_session.query(RequirementAnalysis).count() == 1


def test_continue_analysis_unknown_id_returns_404(client):
    response = client.post(
        "/api/v1/requirements/analyses/not-exist/messages",
        json={"message": "补充"},
    )
    assert response.status_code == 404


def test_export_analysis_markdown(client):
    requirement = _create_requirement(client)
    analysis = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze", json={}
    ).json()["data"]

    response = client.get(f"/api/v1/requirements/analyses/{analysis['id']}/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert "## 一、功能清单" in response.text


def test_export_unknown_analysis_returns_404(client):
    assert (
        client.get("/api/v1/requirements/analyses/not-exist/export").status_code
        == 404
    )
