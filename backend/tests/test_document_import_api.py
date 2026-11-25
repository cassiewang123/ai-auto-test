"""Word/Excel import API tests."""
from __future__ import annotations

import io

from openpyxl import Workbook


def _excel_file() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "接口"
    worksheet.append(["接口名称", "请求方法", "请求URL", "分组", "请求体"])
    worksheet.append(
        [
            "创建用户",
            "POST",
            "/api/v1/users",
            "用户/管理",
            '{"name":"tester"}',
        ]
    )
    worksheet.append(["查询用户", "GET", "/api/v1/users/{id}", "用户/管理", None])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_document_preview_and_import(client):
    preview = client.post(
        "/api/v1/import/document/preview",
        files={
            "file": (
                "interfaces.xlsx",
                _excel_file(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={
            "base_url": "http://api.example.com",
            "path_prefix": "/api/v1",
        },
    )

    assert preview.status_code == 200
    preview_data = preview.json()["data"]
    assert preview_data["total"] == 2
    assert preview_data["file_type"] == "xlsx"
    assert preview_data["methods"] == {"GET": 1, "POST": 1}
    assert preview_data["groups"] == ["用户/管理"]
    selected = preview_data["interfaces"][:1]

    imported = client.post(
        "/api/v1/import/document/import",
        json={"selected_interfaces": selected},
    )

    assert imported.status_code == 200
    result = imported.json()["data"]
    assert result["created_count"] == 1
    case_id = result["case_ids"][0]

    case = client.get(f"/api/v1/test-cases/{case_id}").json()["data"]
    assert case["title"] == "创建用户"
    assert case["method"] == "POST"
    assert case["url"] == "http://api.example.com/api/v1/users"
    assert case["body"] == {"name": "tester"}
    assert case["markers"] == ["api", "document_imported"]
    assert case["assertions"][0]["expected"] == "200"


def test_document_preview_rejects_legacy_word(client):
    response = client.post(
        "/api/v1/import/document/preview",
        files={"file": ("interfaces.doc", b"legacy", "application/msword")},
    )

    assert response.status_code == 422
    assert ".docx" in response.json()["message"]
