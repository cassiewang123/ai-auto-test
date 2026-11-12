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


def test_saved_case_base64_file_is_decoded_for_multipart():
    payload = b"PK\x03\x04saved-workbook"

    converted = RequestBuilder._convert_files(
        [
            {
                "field": "upload",
                "filename": "report.xlsx",
                "content_type": (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                "content_base64": base64.b64encode(payload).decode("ascii"),
            }
        ]
    )

    assert converted[0][0] == "upload"
    assert converted[0][1][1] == payload


def test_saved_file_is_sent_as_real_multipart_upload():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content_type"] = request.headers.get("content-type", "")
        captured["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    payload = b"PK\x03\x04uploaded-workbook"
    builder = RequestBuilder(transport=httpx.MockTransport(handler))
    builder.send(
        RequestDefinition(
            method="POST",
            url="https://example.com/import",
            headers={"Content-Type": "application/json"},
            files=[
                {
                    "field": "file",
                    "filename": "report.xlsx",
                    "content_type": "application/octet-stream",
                    "content_base64": base64.b64encode(payload).decode("ascii"),
                }
            ],
        ),
        {},
    )

    assert str(captured["content_type"]).startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="report.xlsx"' in captured["body"]
    assert payload in captured["body"]


def test_percent_encoded_filename_is_decoded_and_shortened_to_basename():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.7",
            headers={
                "content-type": "application/pdf",
                "content-disposition": (
                    'attachment; filename="%2Fu01%2FapiService%2F'
                    '%E6%A3%80%E6%9F%A5%E6%8A%A5%E5%91%8A.pdf"'
                ),
            },
        )

    response = RequestBuilder(transport=httpx.MockTransport(handler)).send(
        RequestDefinition(method="GET", url="https://example.com/download"),
        {},
    )

    assert response.body["filename"] == "检查报告.pdf"
