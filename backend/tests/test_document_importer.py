"""Word/Excel API document parser tests."""
from __future__ import annotations

import io

import pytest
from docx import Document
from openpyxl import Workbook

from app.services.document_importer import (
    UnsupportedDocumentError,
    parse_interface_document,
)


def _excel_document() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "接口列表"
    worksheet.append(
        [
            "接口名称",
            "请求方法",
            "请求URL",
            "分组",
            "请求头",
            "查询参数",
            "请求体",
            "期望状态码",
        ]
    )
    worksheet.append(
        [
            "查询用户",
            "GET",
            "/v1/users/{id}",
            "用户/查询",
            '{"epToken":"{{epToken}}"}',
            "verbose=true",
            None,
            201,
        ]
    )
    worksheet.append(
        [
            "创建订单",
            "POST",
            "/v1/orders?source=test",
            "订单/创建",
            None,
            "channel=web",
            '{"sku":"A001","count":2}',
            200,
        ]
    )
    worksheet.append(["标题行", "不是接口", "/v1/ignored", "杂项"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _word_document() -> bytes:
    document = Document()
    document.add_heading("订单服务", level=1)
    table = document.add_table(rows=1, cols=4)
    for index, value in enumerate(["接口名称", "请求方法", "请求URL", "分组"]):
        table.rows[0].cells[index].text = value
    row = table.add_row().cells
    row[0].text = "查询订单"
    row[1].text = "GET"
    row[2].text = "/v2/orders/{id}"
    row[3].text = "订单/查询"
    document.add_paragraph("创建订单 POST /v2/orders")
    document.add_paragraph("接口名称：删除订单")
    document.add_paragraph("请求方法：DELETE")
    document.add_paragraph("请求URL：/v2/orders/{id}")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_parse_excel_document_with_common_chinese_headers():
    endpoints, warnings = parse_interface_document(
        "interfaces.xlsx",
        _excel_document(),
        base_url="http://api.example.com/",
        path_prefix="/v1",
    )

    assert warnings == []
    assert len(endpoints) == 2
    first, second = endpoints
    assert first["method"] == "GET"
    assert first["url"] == "http://api.example.com/v1/users/{{id}}"
    assert first["headers"] == {"epToken": "{{epToken}}"}
    assert first["params"] == {"verbose": "true"}
    assert first["expected_status"] == 201
    assert first["group_path"] == "用户/查询"
    assert second["body"] == {"sku": "A001", "count": 2}
    assert second["params"] == {"source": "test", "channel": "web"}
    assert second["headers"]["Content-Type"] == "application/json"


def test_parse_word_tables_and_inline_paragraphs():
    endpoints, warnings = parse_interface_document(
        "interfaces.docx",
        _word_document(),
        base_url="https://api.example.com",
    )

    assert not any("未识别" in warning for warning in warnings)
    assert len(endpoints) == 3
    keys = {(item["method"], item["url"]) for item in endpoints}
    assert ("GET", "https://api.example.com/v2/orders/{{id}}") in keys
    assert ("POST", "https://api.example.com/v2/orders") in keys
    assert ("DELETE", "https://api.example.com/v2/orders/{{id}}") in keys
    deleted = next(item for item in endpoints if item["method"] == "DELETE")
    assert deleted["suggested_name"] == "删除订单"


def test_reject_unsupported_and_corrupt_documents():
    with pytest.raises(UnsupportedDocumentError, match=r"\.docx"):
        parse_interface_document("legacy.doc", b"not-supported")

    with pytest.raises(UnsupportedDocumentError, match="有效"):
        parse_interface_document("broken.xlsx", b"not-a-zip")
