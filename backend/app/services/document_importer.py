"""Parse API definitions from Word (.docx) and Excel (.xlsx) documents.

Word and Excel files do not have a universal API-description standard. This
module therefore supports two explicit, predictable layouts:

* Excel: a worksheet with a header row containing at least an interface path
  column. Common Chinese and English column names are accepted.
* Word: tables using the same columns, plus paragraphs such as
  ``POST /v1/orders`` or ``请求方法：POST`` followed by ``请求URL：/v1/orders``.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from docx import Document
from openpyxl import load_workbook

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_SCAN_ROWS = 5000
MAX_ENDPOINTS = 2000
MAX_WARNINGS = 50

SUPPORTED_EXTENSIONS = {".docx", ".xlsx"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

_FIELD_ALIASES = {
    "method": {
        "method", "httpmethod", "请求方法", "请求方式", "方法", "http请求方式",
    },
    "path": {
        "url", "path", "endpoint", "接口地址", "接口路径", "请求url",
        "请求地址", "请求路径", "路径", "服务地址",
    },
    "name": {
        "name", "title", "接口名称", "接口名", "名称", "用例名称", "标题",
    },
    "description": {
        "description", "desc", "remark", "memo", "描述", "说明", "接口描述",
        "备注", "备注说明",
    },
    "group": {
        "group", "group_path", "module", "folder", "分组", "分组路径",
        "模块", "业务模块", "目录",
    },
    "headers": {"headers", "header", "请求头", "header参数", "请求头参数"},
    "params": {
        "params", "query", "queryparams", "参数", "请求参数", "查询参数",
        "query参数", "url参数",
    },
    "body": {
        "body", "payload", "requestbody", "请求体", "请求body", "请求报文", "入参",
    },
    "expected_status": {
        "status", "statuscode", "expectedstatus", "期望状态码", "响应状态码",
        "期望http状态码",
    },
}

_HEADER_LOOKUP = {
    alias: field
    for field, aliases in _FIELD_ALIASES.items()
    for alias in aliases
}

_LABEL_LOOKUP = {
    **_HEADER_LOOKUP,
    "接口": "name",
    "接口说明": "description",
    "业务模块": "group",
}

_INLINE_ENDPOINT_RE = re.compile(
    r"(?i)(?<![A-Z])(GET|POST|PUT|PATCH|DELETE)\s+"
    r"((?:https?://|//|/|\{\{)[^\s，。；;、|]+)"
)
_METHOD_LABEL_RE = re.compile(
    r"(?i)(?:请求方法|请求方式|http\s*方法|method)\s*[:：]\s*"
    r"(GET|POST|PUT|PATCH|DELETE)"
)
_PATH_LABEL_RE = re.compile(
    r"(?i)(?:请求\s*url|请求地址|接口地址|接口路径|服务地址|url|path)"
    r"\s*[:：]\s*((?:https?://|//|/|\{\{)[^\s，。；;]+)"
)
_LABEL_RE = re.compile(r"^\s*([^:：]{1,24})\s*[:：]\s*(.+?)\s*$")


class UnsupportedDocumentError(ValueError):
    """Raised when the uploaded file is not a supported Office document."""


def _normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s_\-/\\:：()（）\[\]【】]+", "", text)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _add_warning(warnings: list[str], message: str) -> None:
    if len(warnings) >= MAX_WARNINGS or message in warnings:
        return
    warnings.append(message)


def _header_map(values: list[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for index, value in enumerate(values):
        field = _HEADER_LOOKUP.get(_normalize_label(value))
        if field and field not in result:
            result[field] = index
    return result


def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    best: tuple[int, dict[str, int]] | None = None
    for index, row in enumerate(rows[:30]):
        mapping = _header_map(row)
        if "path" not in mapping:
            continue
        if best is None or len(mapping) > len(best[1]):
            best = (index, mapping)
    return best


def _value_at(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _rows_to_records(
    rows: list[list[str]],
    source: str,
    warnings: list[str],
) -> list[dict[str, str]]:
    header = _find_header(rows)
    if not header:
        if any(any(cell for cell in row) for row in rows):
            _add_warning(warnings, f"{source} 未识别到接口表头，需要包含“请求方法/请求URL”等列")
        return []

    header_index, mapping = header
    records: list[dict[str, str]] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(cell for cell in row):
            continue
        repeated_header = _header_map(row)
        if repeated_header.get("path") == mapping.get("path"):
            continue
        record = {
            field: _value_at(row, index)
            for field, index in mapping.items()
        }
        if not record.get("path") and not record.get("name"):
            continue
        record["_row"] = str(row_number)
        record["_source"] = source
        records.append(record)
    return records


def _parse_mapping(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        value = None
    return value if isinstance(value, dict) else None


def _parse_headers(raw: str) -> dict[str, str]:
    parsed = _parse_mapping(raw)
    if parsed is not None:
        return {str(key): _cell_text(value) for key, value in parsed.items()}

    headers: dict[str, str] = {}
    for line in re.split(r"[\r\n;；]+", raw):
        if ":" not in line and "：" not in line:
            continue
        key, value = re.split(r"[:：]", line, maxsplit=1)
        if key.strip():
            headers[key.strip()] = value.strip()
    return headers


def _parse_params(raw: str) -> dict[str, Any]:
    parsed = _parse_mapping(raw)
    if parsed is not None:
        return parsed

    text = raw.strip().lstrip("?")
    if not text:
        return {}
    return dict(parse_qsl(text, keep_blank_values=True))


def _parse_body(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text


def _normalize_method(raw: str, warnings: list[str], label: str) -> str | None:
    method = raw.strip().upper()
    if not method:
        _add_warning(warnings, f"{label} 未填写请求方法，已按 GET 处理")
        return "GET"
    if method not in HTTP_METHODS:
        # 无效方法多为文档中的标题/杂项行，静默跳过，避免误报警告。
        return None
    return method


def _normalize_path_templates(path: str) -> str:
    # Convert OpenAPI-style {id} placeholders without touching {{workspaceVar}}.
    return re.sub(
        r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_.-]*)\}(?!\})",
        r"{{\1}}",
        path,
    )


def _join_url(base_url: str, path: str) -> str:
    path = path.strip()
    if path.startswith(("http://", "https://", "//")):
        return path
    base = base_url.strip()
    if not base:
        return path
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _derive_group(path: str) -> str:
    clean_path = urlsplit(path).path
    parts = [
        part
        for part in clean_path.strip("/").split("/")
        if part and not part.startswith(("{", "{{"))
    ]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0] if parts else "文档导入"


def _normalize_record(
    record: dict[str, str],
    base_url: str,
    path_prefix: str,
    warnings: list[str],
) -> dict[str, Any] | None:
    source = record.get("_source", "文档")
    row = record.get("_row")
    label = f"{source} 第 {row} 行" if row else source

    method = _normalize_method(record.get("method", ""), warnings, label)
    if method is None:
        return None

    path = _normalize_path_templates(record.get("path", "").strip())
    if not path:
        if record.get("name"):
            _add_warning(warnings, f"{label} 缺少请求 URL，已跳过")
        return None

    full_url = _join_url(base_url, path)
    split = urlsplit(full_url)
    params = _parse_params(record.get("params", ""))
    query_params = dict(parse_qsl(split.query, keep_blank_values=True))
    params = {**query_params, **params}
    full_url = urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))

    parsed_path = urlsplit(full_url).path
    if path_prefix and not parsed_path.startswith(path_prefix):
        return None

    headers = _parse_headers(record.get("headers", ""))
    body = _parse_body(record.get("body", ""))
    if isinstance(body, (dict, list)) and not any(
        key.lower() == "content-type" for key in headers
    ):
        headers["Content-Type"] = "application/json"

    expected_raw = record.get("expected_status", "").strip()
    try:
        expected_status = int(expected_raw) if expected_raw else 200
    except ValueError:
        expected_status = 200
        _add_warning(warnings, f"{label} 的期望状态码不是数字，已按 200 处理")
    if not 100 <= expected_status <= 599:
        expected_status = 200
        _add_warning(warnings, f"{label} 的期望状态码超出范围，已按 200 处理")

    name = record.get("name", "").strip() or f"{method} {parsed_path or path}"
    group = record.get("group", "").strip() or _derive_group(parsed_path or path)
    description = record.get("description", "").strip()
    if not description:
        description = f"从 {source} 导入：{method} {parsed_path or path}"

    return {
        "suggested_name": name,
        "method": method,
        "path": parsed_path or path,
        "url": full_url,
        "headers": headers,
        "params": params,
        "body": body,
        "description": description,
        "group_path": group,
        "expected_status": expected_status,
        "source": source,
    }


def _extract_excel(data: bytes, warnings: list[str]) -> list[dict[str, str]]:
    workbook = load_workbook(
        io.BytesIO(data),
        read_only=True,
        data_only=True,
    )
    records: list[dict[str, str]] = []
    try:
        for worksheet in workbook.worksheets:
            rows = [
                [_cell_text(value) for value in row]
                for index, row in enumerate(worksheet.iter_rows(values_only=True))
                if index < MAX_SCAN_ROWS
            ]
            records.extend(_rows_to_records(rows, f"Excel/{worksheet.title}", warnings))
            if len(records) >= MAX_ENDPOINTS:
                _add_warning(warnings, f"文档接口过多，仅处理前 {MAX_ENDPOINTS} 条")
                break
    finally:
        workbook.close()
    return records[:MAX_ENDPOINTS]


def _paragraph_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    method_match = _METHOD_LABEL_RE.search(text)
    if method_match:
        metadata["method"] = method_match.group(1)
    path_match = _PATH_LABEL_RE.search(text)
    if path_match:
        metadata["path"] = path_match.group(1).rstrip("，。；;、")

    label_match = _LABEL_RE.match(text)
    if label_match:
        field = _LABEL_MAP_NORMALIZED.get(_normalize_label(label_match.group(1)))
        if field:
            metadata[field] = label_match.group(2).strip()
    return metadata


_LABEL_MAP_NORMALIZED = {
    _normalize_label(alias): field
    for alias, field in _LABEL_LOOKUP.items()
}


def _extract_word_paragraphs(
    document: Document,
    warnings: list[str],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    pending: dict[str, str] = {}
    current_group = "Word 文档"

    def flush() -> None:
        nonlocal pending
        if pending.get("path"):
            pending.setdefault("group", current_group)
            pending["_source"] = "Word/正文"
            records.append(dict(pending))
        pending = {}

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = (paragraph.style.name if paragraph.style else "").lower()
        if style_name.startswith(("heading", "标题")):
            current_group = text
            continue

        direct_matches = list(_INLINE_ENDPOINT_RE.finditer(text))
        if direct_matches:
            for match in direct_matches:
                title = text[: match.start()].strip(" -:：,，")
                records.append(
                    {
                        "name": title,
                        "method": match.group(1).upper(),
                        "path": match.group(2).rstrip("，。；;、"),
                        "group": current_group,
                        "_source": "Word/正文",
                    }
                )
            continue

        metadata = _paragraph_metadata(text)
        if metadata:
            pending.update(metadata)
            if pending.get("method") and pending.get("path"):
                flush()
    flush()
    if not records:
        _add_warning(warnings, "Word 正文未识别到“POST /path”或“请求方法 + 请求URL”格式的接口")
    return records


def _extract_word_tables(
    document: Document,
    warnings: list[str],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for table_index, table in enumerate(document.tables, start=1):
        rows = [
            [_cell_text(cell.text) for cell in row.cells]
            for row in table.rows[:MAX_SCAN_ROWS]
        ]
        records.extend(
            _rows_to_records(rows, f"Word/表格{table_index}", warnings)
        )
        if len(records) >= MAX_ENDPOINTS:
            _add_warning(warnings, f"文档接口过多，仅处理前 {MAX_ENDPOINTS} 条")
            break
    return records[:MAX_ENDPOINTS]


def _extract_word(data: bytes, warnings: list[str]) -> list[dict[str, str]]:
    document = Document(io.BytesIO(data))
    records = _extract_word_tables(document, warnings)
    records.extend(_extract_word_paragraphs(document, warnings))
    return records[:MAX_ENDPOINTS]


def _assert_safe_archive(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            uncompressed = sum(item.file_size for item in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise UnsupportedDocumentError("文件不是有效的 Word/Excel 文档") from exc
    if uncompressed > MAX_UNCOMPRESSED_BYTES:
        raise UnsupportedDocumentError("文档解压后超过 100 MB，已拒绝解析")


def parse_interface_document(
    filename: str,
    data: bytes,
    *,
    base_url: str = "",
    path_prefix: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse supported Office documents into importable interface dictionaries."""
    extension = Path(filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError("仅支持 .docx 和 .xlsx 文件")
    if not data:
        raise UnsupportedDocumentError("上传文件为空")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise UnsupportedDocumentError("文件超过 10 MB，已拒绝解析")
    _assert_safe_archive(data)

    warnings: list[str] = []
    if extension == ".xlsx":
        records = _extract_excel(data, warnings)
    else:
        records = _extract_word(data, warnings)

    endpoints: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        endpoint = _normalize_record(record, base_url, path_prefix, warnings)
        if endpoint is None:
            continue
        key = (endpoint["method"], endpoint["url"])
        if key in seen:
            continue
        seen.add(key)
        endpoints.append(endpoint)

    if not endpoints:
        _add_warning(
            warnings,
            "未解析到接口。Excel 请使用含“请求方法、请求URL”的表头；"
            "Word 可使用同样表格，或正文“POST /path”格式。",
        )
    return endpoints, warnings
