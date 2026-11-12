"""二进制响应体应标记为可下载文件，避免按文本解码后出现乱码."""

import base64

import httpx
from test_engine.request_builder import RequestBuilder

from app.schemas.execution import RequestDefinition

_XLSX_BYTES = b"PK\x03\x04binary-excel-content"


def _builder() -> RequestBuilder:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_XLSX_BYTES,
            headers={
                "content-type": (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                "content-disposition": 'attachment; filename="export.xlsx"',
            },
        )

    return RequestBuilder(transport=httpx.MockTransport(handler))


def test_binary_response_is_marked_for_download():
    response = _builder().send(
        RequestDefinition(method="GET", url="https://example.com/export"),
        {},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert response.body["__binary__"] is True
    assert response.body["filename"] == "export.xlsx"
    assert response.body["size"] == len(_XLSX_BYTES)
    assert base64.b64decode(response.body["base64"]) == _XLSX_BYTES


def test_text_response_keeps_json_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    response = RequestBuilder(transport=httpx.MockTransport(handler)).send(
        RequestDefinition(method="GET", url="https://example.com/api"),
        {},
    )

    assert response.body == {"ok": True}
    assert response.text


def test_binary_filename_is_inferred_from_workbook_content():
    workbook = b"PK\x03\x04" + b"xl/workbook.xml" + b"payload"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=workbook,
            headers={"content-type": "application/octet-stream"},
        )

    response = RequestBuilder(transport=httpx.MockTransport(handler)).send(
        RequestDefinition(method="POST", url="https://example.com/api/exportExecl"),
        {},
    )

    assert response.body["filename"] == "exportExecl.xlsx"
    assert response.body["content_type"].endswith("spreadsheetml.sheet")
