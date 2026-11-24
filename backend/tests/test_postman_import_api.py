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


def _minimal_collection() -> dict:
    """最小的 Postman v2.1 集合，避免依赖本机文件."""
    return {
        "info": {
            "name": "Demo",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "FolderA",
                "item": [
                    {
                        "name": "ReqA",
                        "request": {
                            "method": "GET",
                            "url": {
                                "raw": "https://example.com/a",
                                "protocol": "https",
                                "host": ["example", "com"],
                                "path": ["a"],
                            },
                            "header": [],
                        },
                    }
                ],
            },
            {
                "name": "FolderB",
                "item": [
                    {
                        "name": "ReqB",
                        "request": {
                            "method": "POST",
                            "url": {
                                "raw": "https://example.com/b",
                                "protocol": "https",
                                "host": ["example", "com"],
                                "path": ["b"],
                            },
                            "header": [],
                        },
                    }
                ],
            },
        ],
        "variable": [],
    }


def test_postman_preview_applies_root_group(client):
    response = client.post(
        "/api/v1/import/postman/preview",
        json={
            "collection": _minimal_collection(),
            "root_group_path": "swgd-imap-content",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    paths = {item["group_path"] for item in data["interfaces"]}
    # 根分组作为前缀，原有 Postman 文件夹层级保留
    assert paths == {
        "swgd-imap-content/FolderA",
        "swgd-imap-content/FolderB",
    }
    assert "swgd-imap-content/FolderA" in data["groups"]


def test_postman_preview_without_root_group_keeps_original_paths(client):
    response = client.post(
        "/api/v1/import/postman/preview",
        json={"collection": _minimal_collection()},
    )
    paths = {item["group_path"] for item in response.json()["data"]["interfaces"]}
    assert paths == {"FolderA", "FolderB"}


def test_postman_preview_root_group_is_idempotent(client):
    """根分组已包含在原路径中时不应重复拼接前缀."""
    collection = _minimal_collection()
    response = client.post(
        "/api/v1/import/postman/preview",
        json={"collection": collection, "root_group_path": "FolderA"},
    )
    paths = {item["group_path"] for item in response.json()["data"]["interfaces"]}
    # FolderA 本身已是路径前缀，不会被拼成 FolderA/FolderA
    assert "FolderA" in paths
    assert "FolderA/FolderB" in paths


def test_postman_import_writes_cases_into_root_group(client):
    preview = client.post(
        "/api/v1/import/postman/preview",
        json={
            "collection": _minimal_collection(),
            "root_group_path": "导入根分组",
        },
    ).json()["data"]

    response = client.post(
        "/api/v1/import/postman/import",
        json={
            "selected_interfaces": preview["interfaces"],
            "root_group_path": "导入根分组",
        },
    )
    assert response.status_code == 200
    case_ids = response.json()["data"]["case_ids"]
    assert len(case_ids) == 2

    paths = set()
    for case_id in case_ids:
        case = client.get(f"/api/v1/test-cases/{case_id}").json()["data"]
        paths.add(case["group_path"])
    # 导入时不会二次加前缀
    assert paths == {"导入根分组/FolderA", "导入根分组/FolderB"}
