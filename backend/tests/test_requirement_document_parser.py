"""需求文档解析测试：多格式导入与告警."""

from __future__ import annotations

import io

import pytest
from docx import Document

from app.services.requirement_document_parser import (
    DocumentParseError,
    _clean_pdf_layout,
    _detect_repeated_page_furniture,
    extract_image_data_urls,
    parse_document,
    strip_image_markers,
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
    """图片不做 OCR，但保留原型图本身供多模态模型理解.

    早期实现直接丢弃图片内容（正文为空），导致启用了大模型也无法利用
    页面原型；现在把图以 data URL 存入正文，同时保留 OCR 告警。
    """
    parsed = parse_document("截图.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    assert parsed.file_type == "png"
    assert any("OCR" in warning for warning in parsed.warnings)
    # 正文里保留可被多模态使用的原型图 data URL
    urls = extract_image_data_urls(parsed.content)
    assert len(urls) == 1
    assert urls[0].startswith("data:image/png;base64,")
    # 去掉标记后没有可读文本，仍视为「无文本正文」
    assert strip_image_markers(parsed.content) == ""


def test_parse_corrupt_pdf_raises_parse_error():
    # 损坏的 PDF 必须明确报错，不能静默产出空正文
    with pytest.raises(DocumentParseError):
        parse_document("需求.pdf", b"%PDF-1.4\n" + b"0" * 64)


def test_pdf_backend_prefers_pypdf_then_pdfplumber(monkeypatch):
    """pypdf 缺失时必须自动回退到 pdfplumber，而不是直接报缺库。"""
    from app.services import requirement_document_parser as parser

    calls: list[str] = []

    def fake_pypdf(data, warnings):
        calls.append("pypdf")
        return None  # 模拟未安装

    def fake_pdfplumber(data, warnings):
        calls.append("pdfplumber")
        return ["回退后端提取到的正文"]

    monkeypatch.setattr(parser, "_extract_pdf_with_pypdf", fake_pypdf)
    monkeypatch.setattr(parser, "_extract_pdf_with_pdfplumber", fake_pdfplumber)

    parsed = parser.parse_document("需求.pdf", b"%PDF-1.4\n" + b"0" * 64)
    assert calls == ["pypdf", "pdfplumber"]
    assert "回退后端提取到的正文" in parsed.content
    assert parsed.warnings == []


def test_pdf_reports_warning_when_no_backend_available(monkeypatch):
    """所有后端都缺失时必须给出安装提示，且不产出正文。"""
    from app.services import requirement_document_parser as parser

    monkeypatch.setattr(parser, "_extract_pdf_with_pypdf", lambda *_a, **_k: None)
    monkeypatch.setattr(
        parser, "_extract_pdf_with_pdfplumber", lambda *_a, **_k: None
    )

    parsed = parser.parse_document("需求.pdf", b"%PDF-1.4\n" + b"0" * 64)
    assert parsed.content == ""
    assert any("pip install pypdf" in warning for warning in parsed.warnings)


def test_pdf_scanned_document_warns_about_missing_text(monkeypatch):
    """扫描件（无文本层）应提示补充正文，而不是静默成功。"""
    from app.services import requirement_document_parser as parser

    monkeypatch.setattr(
        parser, "_extract_pdf_with_pypdf", lambda *_a, **_k: ["", "  "]
    )

    parsed = parser.parse_document("扫描件.pdf", b"%PDF-1.4\n" + b"0" * 64)
    assert parsed.is_empty
    assert any("扫描件" in warning for warning in parsed.warnings)


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


# ---------------------------------------------------------------------------
# PDF 版面清理：噪声去除与内容保全
# ---------------------------------------------------------------------------
def test_clean_pdf_layout_removes_page_numbers_and_export_marker():
    pages = [
        "标题行\n正文第一句。\n– 2",
        "标题行\n正文第二句。\n– 3",
        "标题行\n正文第三句。\n– 4",
    ]
    cleaned = _clean_pdf_layout(pages)
    assert "– 2" not in cleaned
    assert "– 3" not in cleaned
    assert "正文第一句。" in cleaned


def test_clean_pdf_layout_removes_toc_noise():
    pages = ["Table of Contents\nNo headings included in this document\n真实内容。"]
    cleaned = _clean_pdf_layout(pages)
    assert "Table of Contents" not in cleaned
    assert "No headings included" not in cleaned
    assert "真实内容。" in cleaned


def test_clean_pdf_layout_removes_repeated_header():
    pages = [
        "公司名 – 需求文档\n内容一。",
        "公司名 – 需求文档\n内容二。",
        "公司名 – 需求文档\n内容三。",
    ]
    cleaned = _clean_pdf_layout(pages)
    assert "公司名 – 需求文档" not in cleaned
    assert "内容一。" in cleaned


def test_clean_pdf_layout_keeps_repeated_body_entries():
    """正文条目在不同分支重复出现时不得被当作页眉删除."""
    pages = [
        "轨迹序号1 对应申报地海关代码。\n轨迹序号2 对应换装地1。",
        "轨迹序号1 对应申报地海关代码。\n轨迹序号2 对应换装地1。",
        "轨迹序号3 对应境内目的地关区代码。\n轨迹序号4 对应境内目的地关区代码。",
        "补充说明内容。\n其他说明。",
    ]
    cleaned = _clean_pdf_layout(pages)
    # 这正是真实需求文档的形态：条目重复但属于正文
    assert cleaned.count("轨迹序号1") == 2
    assert "轨迹序号3" in cleaned


def test_detect_page_furniture_requires_enough_pages():
    # 少于 3 页时不做页眉判定，避免误删唯一内容
    assert _detect_repeated_page_furniture(["头部\n内容。", "头部\n内容。"]) == set()


def test_detect_page_furniture_finds_consistent_header():
    pages = [f"页眉文本\n内容{i}。" for i in range(6)]
    furniture = _detect_repeated_page_furniture(pages)
    assert "页眉文本" in furniture


def test_clean_pdf_layout_merges_soft_wrapped_lines():
    """被硬换行截断的句子应拼回整句，避免功能清单出现碎片."""
    pages = ["页面基本信息：出境运输\n方式代码 对应 excel 中的出境运输方式代码。"]
    cleaned = _clean_pdf_layout(pages)
    assert "出境运输方式代码" in cleaned.replace("\n", "")


def test_clean_pdf_layout_does_not_merge_new_items():
    """以「轨迹序号」「页面」开头的新条目不应并入上一句."""
    pages = ["上一句还没有结束\n轨迹序号1 对应申报地海关代码。"]
    cleaned = _clean_pdf_layout(pages)
    assert "轨迹序号1" in cleaned
    assert "上一句还没有结束轨迹序号1" not in cleaned
