"""Postman Collection 导入器测试."""
from __future__ import annotations

import json

from app.services.postman_importer import parse_postman_collection


def _collection() -> dict:
    return {
        "info": {
            "name": "demo",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "contentProtocol", "value": "http"},
            {"key": "contentHost", "value": "192.168.120.82"},
            {"key": "contentPort", "value": "9002"},
            {"key": "contentContext", "value": "/swgdimapgateway/swgd-imap-content"},
            {"key": "version", "value": "v1"},
            {"key": "epToken", "value": ""},
        ],
        "item": [
            {
                "name": "ApiService 接口调用",
                "item": [
                    {
                        "name": "查询分页",
                        "request": {
                            "method": "POST",
                            "header": [
                                {"key": "epToken", "value": "{{epToken}}"},
                                {"key": "Content-Type", "value": "application/json"},
                            ],
                            "body": {
                                "mode": "raw",
                                "raw": json.dumps({"page": 1, "goodsName": "测试"}),
                                "options": {"raw": {"language": "json"}},
                            },
                            "url": {
                                "raw": "{{contentProtocol}}://{{contentHost}}:{{contentPort}}/{{contentContext}}/{{version}}/apiService/queryPage",
                                "query": [{"key": "current", "value": "1"}],
                            },
                        },
                    },
                    {
                        "name": "下载 PDF",
                        "request": {
                            "method": "GET",
                            "url": {
                                "raw": "{{contentProtocol}}://{{contentHost}}:{{contentPort}}/{{contentContext}}/{{version}}/apiService/downloadPdf/1"
                            },
                        },
                    },
                ],
            },
            {
                "name": "Enterprise 企业",
                "item": [
                    {
                        "name": "保存企业",
                        "request": {
                            "method": "POST",
                            "header": [{"key": "epToken", "value": "{{epToken}}"}],
                            "body": {
                                "mode": "raw",
                                "raw": '{"orgCode": "{{enterpriseCode}}"}',
                            },
                            "url": {
                                "raw": "{{enterpriseProtocol}}://{{enterpriseHost}}:{{enterprisePort}}/{{version}}/enterprise/invokeEnterpriseAccreSuccess"
                            },
                        },
                    }
                ],
            },
        ],
    }


def test_parses_folder_hierarchy_and_requests():
    endpoints, warnings, variables = parse_postman_collection(_collection())

    assert warnings == []
    assert len(endpoints) == 3
    assert variables["contentHost"] == "192.168.120.82"

    first = endpoints[0]
    assert first["method"] == "POST"
    assert first["group_path"] == "ApiService 接口调用"
    assert first["suggested_name"] == "查询分页"
    assert first["headers"]["epToken"] == "{{epToken}}"
    assert first["params"] == {"current": "1"}
    assert first["body"] == {"page": 1, "goodsName": "测试"}
    assert first["variables"] == ["epToken"]

    # GET 请求没有 header 时，集合预请求脚本注入的 epToken 仍然会被补齐
    assert endpoints[1]["headers"]["epToken"] == "{{epToken}}"
    assert endpoints[1]["body"] is None


def test_reports_missing_variables_and_applies_overrides():
    endpoints, _warnings, variables = parse_postman_collection(
        _collection(),
        variables={"epToken": "token-123", "enterpriseHost": "10.0.0.1"},
    )

    assert variables["epToken"] == "token-123"
    assert endpoints[0]["variables"] == []
    enterprise = endpoints[2]
    assert enterprise["resolved_variables"]["enterpriseHost"] == "10.0.0.1"
    # 集合未定义、调用方也未提供的变量会被标记出来
    assert enterprise["variables"] == [
        "enterpriseProtocol",
        "enterprisePort",
        "enterpriseCode",
    ]

    complete, _warnings, _variables = parse_postman_collection(
        _collection(),
        variables={
            "epToken": "token-123",
            "enterpriseProtocol": "http",
            "enterpriseHost": "10.0.0.1",
            "enterprisePort": "8080",
            "enterpriseCode": "ORG001",
        },
    )
    assert complete[2]["variables"] == []


def test_formdata_files_are_marked_for_manual_upload():
    collection = {
        "info": {"schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [
            {
                "name": "上传文件",
                "request": {
                    "method": "POST",
                    "body": {
                        "mode": "formdata",
                        "formdata": [
                            {"key": "file", "type": "file", "src": ""},
                            {"key": "bizType", "type": "text", "value": "content"},
                        ],
                    },
                    "url": "http://localhost:9002/upload",
                },
            }
        ],
    }

    endpoints, _warnings, _variables = parse_postman_collection(collection)

    assert endpoints[0]["has_upload"] is True
    assert endpoints[0]["body"] == {"bizType": "content"}
    assert endpoints[0]["files"][0]["field"] == "file"


def test_rejects_unsupported_schema():
    try:
        parse_postman_collection(
            {"info": {"schema": "https://schema.getpostman.com/json/collection/v1.0.0/collection.json"}, "item": []}
        )
    except ValueError as exc:
        assert "仅支持 Postman Collection v2.x" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("应当拒绝不支持的 schema")
