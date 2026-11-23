"""需求/知识库文档解析：把多种格式统一解析为纯文本.

文档「一、需求管理」要求支持 PDF、Word、Markdown、纯文本，以及图片格式的
需求导入。本模块统一入口 :func:`parse_document`：

- ``.docx``  使用 python-docx（项目已有依赖），保留段落与表格文字；
- ``.pdf``   依次尝试 pypdf、pdfplumber；两者都未安装时给出明确告警，不静默产出空文本；
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
    "未安装 PDF 解析库（pypdf / pdfplumber），无法解析 PDF 正文；"
    "请执行 pip install pypdf 后重新上传"
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

    # 库缺失返回 None，库解析失败抛 DocumentParseError；两种都继续尝试下一个后端，
    # 只有全部后端都不可用时才抛出错误，避免一个后端的兼容性问题阻断整条链路。
    errors: list[str] = []
    pages: list[str] | None = None
    for backend in (_extract_pdf_with_pypdf, _extract_pdf_with_pdfplumber):
        try:
            pages = backend(data, warnings)
        except DocumentParseError as exc:
            errors.append(str(exc))
            warnings.clear()
            continue
        if pages is not None:
            break

    if pages is None:
        if errors:
            raise DocumentParseError(errors[0])
        _add_warning(warnings, _PDF_LIB_WARNING)
        return ""

    text_pages = [page.strip() for page in pages if page and page.strip()]
    if not text_pages:
        _add_warning(
            warnings,
            "PDF 未提取到文本，可能是扫描件或纯图片 PDF，请补充文本内容",
        )
        return ""
    return _clean_pdf_layout(text_pages)


# 页码纯数字行，如 "– 2"、"- 3 -"、"12"
_PAGE_NUMBER_RE = re.compile(r"^[\s–—\-·]*(?:\d{1,4}|[ivxlcdm]{1,6})[\s–—\-·]*$", re.I)
_EXPORT_MARKER_RE = re.compile(r"^(?:Exported on|导出时间|打印时间)\b", re.I)
_NAV_NOISE_RE = re.compile(
    r"^(?:Table of Contents|No headings included in this document|目录)$", re.I
)
# 以这些标点结尾表示句子已结束，不需要拼接下一行
_SENTENCE_END = tuple("。！？；：:;!?.")
# 以这些字符开头的行属于上一行的续行
_CONTINUATION_START = tuple("，,、）)】}」』”’")


def _clean_pdf_layout(pages: list[str]) -> str:
    """清理 PDF 版面噪声，并把被硬换行截断的句子拼回整句.

    PDF 按视觉行输出文本，一段话常被拆成多行；直接按句号切分会把「出境运输\\n
    方式代码」这类内容拆成两个半句，导致功能清单出现碎片。这里先去掉页码、
    导出标记、重复页眉等噪声，再合并应当连续的软换行。
    """
    # 1. 去掉页码/导出标记/目录提示等噪声行
    cleaned_lines: list[str] = []
    for page in pages:
        for raw_line in page.splitlines():
            line = raw_line.strip()
            if not line:
                cleaned_lines.append("")
                continue
            if _PAGE_NUMBER_RE.match(line) or _EXPORT_MARKER_RE.match(line):
                continue
            if _NAV_NOISE_RE.match(line):
                continue
            cleaned_lines.append(line)

    # 2. 去掉页眉页脚：仅当整行在多个页面的首/末行重复出现时才判定为版面装饰。
    #    不能按「任意重复」删除——需求文档里「轨迹序号1…」这类条目天然会在多个
    #    分支中重复出现，按重复删除会丢失真实内容。
    headers_footers = _detect_repeated_page_furniture(pages)

    # 3. 合并软换行：只有明确的「被硬换行截断」才拼接
    merged: list[str] = []
    for line in cleaned_lines:
        if not line:
            merged.append("")
            continue
        if line in headers_footers:
            continue
        if merged and merged[-1]:
            previous = merged[-1]
            previous_open = not previous.endswith(_SENTENCE_END)
            current_continues = (
                line[0] in _CONTINUATION_START
                or len(line) < 30
                or len(previous) < 20
            )
            looks_new_item = bool(re.match(r"^(?:\d+[.、]|轨迹序号|序号|页面|换装地)", line))
            if previous_open and current_continues and not looks_new_item:
                merged[-1] = previous + line
                continue
        merged.append(line)

    return "\n".join(merged).strip()


def _detect_repeated_page_furniture(pages: list[str]) -> set[str]:
    """识别真正的页眉/页脚：在多页首行或末行重复出现的短文本.

    只有版面装饰才会稳定出现在每页的固定位置；正文条目即便内容重复，
    也不会都落在首/末行，因此这种判定不会误删需求内容。
    """
    if len(pages) < 3:
        return set()

    edge_counts: dict[str, int] = {}
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        if not lines:
            continue
        for candidate in {lines[0], lines[-1]}:
            if len(candidate) <= 60:
                edge_counts[candidate] = edge_counts.get(candidate, 0) + 1

    threshold = max(3, len(pages) // 2)
    return {
        line for line, count in edge_counts.items() if count >= threshold
    }


def _extract_pdf_with_pypdf(data: bytes, warnings: list[str]) -> list[str] | None:
    """首选 pypdf；未安装时返回 None 交给下一个实现。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise DocumentParseError(f"PDF 文档解析失败: {exc}") from exc

    pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            _add_warning(warnings, f"第 {page_number} 页文本提取失败，已跳过")
            pages.append("")
    return pages


def _extract_pdf_with_pdfplumber(
    data: bytes, warnings: list[str]
) -> list[str] | None:
    """次选 pdfplumber；未安装时返回 None。"""
    try:
        import pdfplumber
    except ImportError:
        return None

    pages: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    pages.append(page.extract_text() or "")
                except Exception:
                    _add_warning(warnings, f"第 {page_number} 页文本提取失败，已跳过")
                    pages.append("")
    except Exception as exc:
        raise DocumentParseError(f"PDF 文档解析失败: {exc}") from exc
    return pages


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
