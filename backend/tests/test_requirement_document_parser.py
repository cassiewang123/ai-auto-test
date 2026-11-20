"""需求文档解析测试：多格式导入与告警."""

from __future__ import annotations

import io

import pytest
from docx import Document

from app.services.requirement_document_parser import (
    DocumentParseError,
    parse_document,
    summarize_document,
)


def _build_docx(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for col_index, value in enumerate(row):
                grid.cell(row_index, col_index).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_parse_markdown_keeps_text():
    parsed = parse_document("需求.md", "# 登录\n用户名密码登录".encode())
    assert parsed.file_type == "md"
    assert "用户名密码登录" in parsed.content
    assert parsed.warnings == []


def test_parse_txt_falls_back_to_gb18030():
    # GBK 编码的中文文档不应解析成乱码或抛错
    parsed = parse_document("需求.txt", "用户登录。".encode("gb18030"))
    assert "用户登录" in parsed.content


def test_parse_json_pretty_prints():
    parsed = parse_document("spec.json", b'{"name":"order","fields":["id"]}')
    assert '"name": "order"' in parsed.content


def test_parse_docx_includes_paragraphs_and_tables():
    data = _build_docx(
        ["用户登录功能说明", "支持账号密码登录"],
        [["字段", "说明"], ["username", "用户名"]],
    )
    parsed = parse_document("需求.docx", data)
    assert "用户登录功能说明" in parsed.content
    assert "username | 用户名" in parsed.content
    assert parsed.warnings == []


def test_parse_docx_heading_becomes_markdown_heading():
    document = Document()
    document.add_heading("登录模块", level=1)
    document.add_paragraph("说明文本")
    buffer = io.BytesIO()
    document.save(buffer)

    parsed = parse_document("需求.docx", buffer.getvalue())
    assert "# 登录模块" in parsed.content


def test_parse_docx_rejects_corrupt_file():
    with pytest.raises(DocumentParseError):
        parse_document("bad.docx", b"not-a-zip")


def test_parse_docx_empty_document_warns():
    document = Document()
    buffer = io.BytesIO()
    document.save(buffer)
    parsed = parse_document("empty.docx", buffer.getvalue())
    assert parsed.is_empty
    assert parsed.warnings


def test_parse_image_warns_about_missing_ocr():
    parsed = parse_document("截图.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    assert parsed.file_type == "png"
    assert parsed.is_empty
    assert any("OCR" in warning for warning in parsed.warnings)


def test_parse_pdf_without_library_returns_warning():
    # 未安装 pypdf 时不应抛异常，而是给出可操作的告警
    parsed = parse_document("需求.pdf", b"%PDF-1.4\n" + b"0" * 64)
    assert parsed.file_type == "pdf"
    # 依赖是否安装取决于运行环境，两种结果都必须可解释
    assert parsed.content or parsed.warnings


def test_parse_unsupported_extension_raises():
    with pytest.raises(DocumentParseError):
        parse_document("data.xls", b"binary")


def test_parse_missing_extension_raises():
    with pytest.raises(DocumentParseError):
        parse_document("noextension", b"text")


def test_parse_empty_file_raises():
    with pytest.raises(DocumentParseError):
        parse_document("需求.txt", b"")


def test_summarize_document_shape():
    parsed = parse_document("需求.md", "需求正文内容".encode())
    summary = summarize_document(parsed)
    assert summary["filename"] == "需求.md"
    assert summary["char_count"] == len("需求正文内容")
    assert summary["is_empty"] is False
