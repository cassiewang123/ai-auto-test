"""需求/知识库文档解析：把多种格式统一解析为纯文本.

文档「一、需求管理」要求支持 PDF、Word、Markdown、纯文本，以及图片格式的
需求导入。本模块统一入口 :func:`parse_document`：

- ``.docx``  使用 python-docx（项目已有依赖），保留段落与表格文字；
- ``.pdf``   使用 pypdf，若未安装则明确提示安装，不静默产出空文本；
- ``.md`` / ``.markdown`` / ``.txt`` / ``.log`` / ``.json`` / ``.csv``
  按 UTF-8（含 BOM）解码，失败回退 GBK，避免中文文档乱码；
- ``.png`` / ``.jpg`` / ``.jpeg`` / ``.webp`` / ``.bmp``
  记录图片本身，但本地不做 OCR，返回告警提示需人工补充正文。

所有解析都带体积上限与告警收集，异常统一转换为 ``DocumentParseError``。
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_WARNINGS = 50

TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".log", ".json", ".csv", ".yaml", ".yml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SUPPORTED_EXTENSIONS = {".pdf", ".docx", *TEXT_EXTENSIONS, *IMAGE_EXTENSIONS}

_IMAGE_OCR_WARNING = "图片格式文档本地不做 OCR，请补充正文文本或改用文本格式文档"
_PDF_LIB_WARNING = (
    "未安装 pypdf，无法解析 PDF 正文；请执行 pip install pypdf 后重新上传"
)


class DocumentParseError(ValueError):
    """文档无法解析（格式不支持、损坏或超出体积限制）."""


@dataclass
class ParsedDocument:
    """文档解析结果."""

    filename: str
    file_type: str
    file_size: int
    content: str
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.content.strip()


def _extension(filename: str) -> str:
    name = (filename or "").strip()
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def _add_warning(warnings: list[str], message: str) -> None:
    if len(warnings) >= MAX_WARNINGS or message in warnings:
        return
    warnings.append(message)


def _truncate(text: str, warnings: list[str]) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    _add_warning(
        warnings,
        f"正文超过 {MAX_TEXT_CHARS} 字符，已截断，请拆分文档后重新上传",
    )
    return text[:MAX_TEXT_CHARS]


def _decode_text(data: bytes) -> str:
    """按 UTF-8(BOM) → UTF-8 → GBK 顺序解码，覆盖中文文档常见编码."""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 各格式解析
# ---------------------------------------------------------------------------
def _parse_text(data: bytes, warnings: list[str]) -> str:
    text = _decode_text(data)
    # JSON 文档格式化后更利于大模型理解结构
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, ValueError):
            return text
    return text


def _parse_docx(data: bytes, warnings: list[str]) -> str:
    """解析 Word：段落 + 表格，按文档顺序拼接."""
    if len(data) > MAX_FILE_BYTES:
        raise DocumentParseError("文档超过 20MB 上限")
    # 先做 zip 炸弹防护，再交给 python-docx 解析
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise DocumentParseError("Word 文档已损坏或不是有效的 .docx 文件") from exc
    if total > MAX_UNCOMPRESSED_BYTES:
        raise DocumentParseError("Word 文档解压后体积过大，已拒绝解析")

    try:
        from docx import Document

        document = Document(io.BytesIO(data))
    except ImportError as exc:  # pragma: no cover - 依赖已在 requirements 中
        raise DocumentParseError("未安装 python-docx，无法解析 Word 文档") from exc
    except Exception as exc:
        raise DocumentParseError(f"Word 文档解析失败: {exc}") from exc

    blocks: list[str] = []
    for paragraph in document.paragraphs:
        line = (paragraph.text or "").strip()
        if not line:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style else ""
        # 标题样式转成 Markdown 标题，便于后续按标题分块
        heading_match = re.match(r"heading (\d+)", style)
        if heading_match:
            level = min(6, max(1, int(heading_match.group(1))))
            blocks.append(f"{'#' * level} {line}")
        else:
            blocks.append(line)

    for table in document.tables:
        rows: list[str] = []
        for row in table.rows:
            cells = [(cell.text or "").strip().replace("\n", " ") for cell in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            blocks.append("\n".join(rows))

    if not blocks:
        _add_warning(warnings, "Word 文档未解析出正文内容，请确认文档是否为空")
    return "\n\n".join(blocks)


def _parse_pdf(data: bytes, warnings: list[str]) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise DocumentParseError("文档超过 20MB 上限")
    try:
        from pypdf import PdfReader
    except ImportError:
        _add_warning(warnings, _PDF_LIB_WARNING)
        return ""

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise DocumentParseError(f"PDF 文档解析失败: {exc}") from exc

    pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            _add_warning(warnings, f"第 {page_number} 页文本提取失败，已跳过")
            continue
        text = text.strip()
        if text:
            pages.append(text)

    if not pages:
        _add_warning(
            warnings,
            "PDF 未提取到文本，可能是扫描件或纯图片 PDF，请补充文本内容",
        )
    return "\n\n".join(pages)


def _parse_image(warnings: list[str]) -> str:
    _add_warning(warnings, _IMAGE_OCR_WARNING)
    return ""


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    """把上传文件解析为纯文本，返回内容与告警."""
    extension = _extension(filename)
    if not extension:
        raise DocumentParseError("无法识别文件类型，请使用 .pdf/.docx/.md/.txt 等格式")
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise DocumentParseError(
            f"不支持的文件类型 {extension}，仅支持: {supported}"
        )
    if not data:
        raise DocumentParseError("文件内容为空")
    if len(data) > MAX_FILE_BYTES:
        raise DocumentParseError("文档超过 20MB 上限")

    warnings: list[str] = []
    if extension == ".docx":
        content = _parse_docx(data, warnings)
    elif extension == ".pdf":
        content = _parse_pdf(data, warnings)
    elif extension in IMAGE_EXTENSIONS:
        content = _parse_image(warnings)
    else:
        content = _parse_text(data, warnings)

    return ParsedDocument(
        filename=filename or f"未命名{extension}",
        file_type=extension.lstrip("."),
        file_size=len(data),
        content=_truncate(content, warnings),
        warnings=warnings,
    )


def image_data_url(filename: str, data: bytes) -> str | None:
    """图片转 data URL，供前端预览（后端不落盘原始图片）."""
    extension = _extension(filename).lstrip(".")
    if extension not in {e.lstrip(".") for e in IMAGE_EXTENSIONS}:
        return None
    import base64

    mime = "jpeg" if extension in {"jpg", "jpeg"} else extension
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


def summarize_document(parsed: ParsedDocument) -> dict[str, Any]:
    """解析结果摘要，供 API 返回前端展示."""
    return {
        "filename": parsed.filename,
        "file_type": parsed.file_type,
        "file_size": parsed.file_size,
        "char_count": len(parsed.content),
        "preview": parsed.content[:500],
        "warnings": parsed.warnings,
        "is_empty": parsed.is_empty,
    }
