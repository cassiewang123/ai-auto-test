"""Postman 导入接口测试（真实集合解析 + 批量创建用例）."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

COLLECTION_PATH = Path(
    r"E:\wxlsoft\WeChat\xwechat_files\wx1015263582_6de7\msg\file\2026-10"
    r"\swgd-imap-content - enterprise.postman_collection.json"
)


def _load_collection() -> dict:
    if not COLLECTION_PATH.exists():
        pytest.skip("本机未找到 swgd-imap-content 集合文件")
    with COLLECTION_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_postman_preview_parses_real_collection(client):
    response = client.post(
        "/api/v1/import/postman/preview",
        json={"collection": _load_collection()},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 135
    assert data["methods"]["POST"] == 131
    assert data["methods"]["GET"] == 4
    assert "swgd-imap-content" in " ".join(data["groups"])
    assert "epToken" in data["unresolved_variables"]
    # 变量值来自集合自身
    assert data["variables"]["contentHost"] == "192.168.120.82"
    assert data["variables"]["contentPort"] == "9002"
    # 5 个文件上传请求需要人工补充文件
    assert data["upload_count"] == 5


def test_postman_import_creates_cases_and_variables(client):
    collection = _load_collection()
    preview = client.post(
        "/api/v1/import/postman/preview",
        json={"collection": collection},
    ).json()["data"]
    selected = preview["interfaces"][:3]

    response = client.post(
        "/api/v1/import/postman/import",
        json={"selected_interfaces": selected, "import_variables": True},
    )

    assert response.status_code == 200
    result = response.json()["data"]
    assert result["created_count"] == 3
    assert len(result["case_ids"]) == 3
    # contentProtocol/contentHost/version 等集合变量会写入工作区变量
    assert result["imported_variables"] >= 5

    case_response = client.get(f"/api/v1/test-cases/{result['case_ids'][0]}")
    assert case_response.status_code == 200
    case = case_response.json()["data"]
    assert case["method"] == "POST"
    assert case["headers"]["epToken"] == "{{epToken}}"
    assert "ApiApplyRecord" in case["group_path"]
    assert case["markers"] == ["api", "postman_imported"]

    variables_response = client.get("/api/v1/variables/?scope=workspace")
    assert variables_response.status_code == 200
    names = {item["name"] for item in variables_response.json()["data"]}
    assert {"contentProtocol", "contentHost", "contentPort", "version"} <= names
