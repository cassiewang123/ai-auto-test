"""知识库（RAG）API 测试：CRUD、文档上传索引、检索与重建."""

from __future__ import annotations

import io

from app.models.knowledge_base import KnowledgeChunk, KnowledgeDocument

DOC_TEXT = """# 登录项目

## 用户登录

用户名与密码校验规则：用户名最小长度 6，最大长度 32；密码最小长度 8。

验证码 4 位，有效期 60 秒。

## 项目管理

创建项目需要填写项目名称与项目描述，创建者自动成为项目管理员。

项目支持归档与恢复，归档后不可再新增测试用例。

## 需求管理

需求文档支持上传 PDF、Word、Markdown 与纯文本，解析后可作为用例生成依据。

需求分析会输出功能清单、界面描述与待澄清项三部分内容。

## 知识库

知识库文档会被切分为多个文本块并建立索引，检索时只召回相关分块。
"""


def _create_kb(client, **overrides):
    payload = {
        "name": "Rain 测试平台",
        "description": "项目技术文档",
        "chunk_strategy": "fixed_window",
        "chunk_size": 200,
        "chunk_overlap": 40,
    }
    payload.update(overrides)
    response = client.post("/api/v1/knowledge-bases", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _upload(client, kb_id, filename="设计文档.md", content=None, category=""):
    data = content if content is not None else DOC_TEXT.encode("utf-8")
    return client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        files={"file": (filename, io.BytesIO(data), "text/markdown")},
        data={"category": category},
    )


def test_knowledge_base_crud(client):
    created = _create_kb(client)
    assert created["name"] == "Rain 测试平台"
    assert created["chunk_size"] == 200
    assert created["document_count"] == 0

    kb_id = created["id"]
    listed = client.get("/api/v1/knowledge-bases")
    assert listed.json()["total"] == 1

    updated = client.put(
        f"/api/v1/knowledge-bases/{kb_id}",
        json={"name": "改个名字", "chunk_size": 300},
    )
    assert updated.json()["data"]["chunk_size"] == 300

    detail = client.get(f"/api/v1/knowledge-bases/{kb_id}")
    assert detail.json()["data"]["name"] == "改个名字"

    deleted = client.delete(f"/api/v1/knowledge-bases/{kb_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/knowledge-bases/{kb_id}").status_code == 404


def test_knowledge_base_rejects_invalid_chunk_size(client):
    response = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "非法参数", "chunk_size": 10},
    )
    assert response.status_code == 422


def test_knowledge_base_rejects_overlap_not_smaller_than_size(client):
    response = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "非法重叠", "chunk_size": 400, "chunk_overlap": 400},
    )
    assert response.status_code == 422
    assert "重叠" in response.json()["message"]


def test_upload_document_builds_index(client, db_session):
    # 用 120 字符窗口确保样本被切成多块，验证的是切分链路而不是单块特例
    kb = _create_kb(client, chunk_size=120, chunk_overlap=20)
    response = _upload(client, kb["id"], category="设计文档")
    assert response.status_code == 200, response.text
    document = response.json()["data"]
    assert document["status"] == "indexed"
    assert document["chunk_count"] > 1
    assert document["category"] == "设计文档"

    chunks = db_session.query(KnowledgeChunk).filter_by(
        document_id=document["id"]
    ).count()
    assert chunks == document["chunk_count"]


def test_upload_unsupported_extension_is_rejected(client):
    kb = _create_kb(client)
    # .xls 现已支持（返回告警而非拒绝），这里改用确实不支持的扩展名
    response = _upload(client, kb["id"], filename="data.exe", content=b"binary")
    assert response.status_code == 422


def test_upload_image_returns_ocr_warning(client):
    kb = _create_kb(client)
    response = _upload(
        client, kb["id"], filename="截图.png", content=b"\x89PNG\r\n\x1a\n"
    )
    assert response.status_code == 200
    document = response.json()["data"]
    assert document["warnings"]
    # 图片不做 OCR，但原型图本身会存入正文并建立索引（可被多模态模型使用），
    # 因此状态是 indexed 而不是 failed。
    assert document["status"] == "indexed"


def test_list_and_delete_document(client, db_session):
    kb = _create_kb(client)
    document = _upload(client, kb["id"]).json()["data"]

    listed = client.get(f"/api/v1/knowledge-bases/{kb['id']}/documents")
    assert listed.json()["total"] == 1

    chunks = client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/documents/{document['id']}/chunks"
    )
    assert chunks.json()["total"] == document["chunk_count"]

    assert (
        client.delete(
            f"/api/v1/knowledge-bases/{kb['id']}/documents/{document['id']}"
        ).status_code
        == 200
    )
    assert db_session.get(KnowledgeDocument, document["id"]) is None
    assert (
        db_session.query(KnowledgeChunk)
        .filter_by(document_id=document["id"])
        .count()
        == 0
    )


def test_retrieve_returns_relevant_chunks(client):
    kb = _create_kb(client)
    _upload(client, kb["id"])

    response = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/retrieve",
        params={"query": "用户名长度校验", "top_k": 3},
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["hit_count"] > 0
    assert result["hits"][0]["score"] > 0
    assert any("用户名" in hit["content"] for hit in result["hits"])
    assert result["query_tokens"]


def test_retrieve_with_empty_query_returns_no_hits(client):
    kb = _create_kb(client)
    _upload(client, kb["id"])
    # 只有停用词的查询无法产生检索词
    response = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/retrieve",
        params={"query": "???"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["hit_count"] == 0


def test_retrieve_unknown_knowledge_base_returns_404(client):
    response = client.post(
        "/api/v1/knowledge-bases/not-exist/retrieve",
        params={"query": "登录"},
    )
    assert response.status_code == 404


def test_rebuild_index_applies_new_chunk_size(client):
    kb = _create_kb(client)
    _upload(client, kb["id"])

    client.put(
        f"/api/v1/knowledge-bases/{kb['id']}",
        json={"chunk_size": 120, "chunk_overlap": 20},
    )
    response = client.post(f"/api/v1/knowledge-bases/{kb['id']}/rebuild-index")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["document_count"] == 1
    assert data["chunk_count"] > 0
    assert data["failed_count"] == 0


def test_reindex_single_document(client):
    kb = _create_kb(client)
    document = _upload(client, kb["id"]).json()["data"]
    before = document["chunk_count"]

    client.put(f"/api/v1/knowledge-bases/{kb['id']}", json={"chunk_size": 120})
    response = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/documents/{document['id']}/reindex"
    )
    assert response.status_code == 200
    assert response.json()["data"]["chunk_count"] >= before


def test_chunk_preview_returns_chunks(client):
    response = client.post(
        "/api/v1/knowledge-bases/chunk-preview",
        json={
            "text": "第一段内容。\n\n第二段内容。\n\n第三段内容。",
            "chunk_strategy": "paragraph",
            "chunk_size": 400,
            "chunk_overlap": 0,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["chunk_count"] >= 1
    assert data["chunks"][0]["char_count"] > 0


def test_chunk_preview_rejects_bad_parameters(client):
    response = client.post(
        "/api/v1/knowledge-bases/chunk-preview",
        json={"text": "内容", "chunk_size": 400, "chunk_overlap": 500},
    )
    assert response.status_code == 422


def test_document_belongs_to_its_knowledge_base(client):
    kb1 = _create_kb(client, name="知识库一")
    kb2 = _create_kb(client, name="知识库二")
    document = _upload(client, kb1["id"]).json()["data"]

    # 跨库访问文档必须 404，避免越权读取
    response = client.get(
        f"/api/v1/knowledge-bases/{kb2['id']}/documents/{document['id']}/chunks"
    )
    assert response.status_code == 404
