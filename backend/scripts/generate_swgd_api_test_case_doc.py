#!/usr/bin/env python3
"""Generate the SWGD IMAP API test-case document as a Word file."""
from __future__ import annotations

import importlib.util
import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[2]
CASE_MODULE_PATH = Path(__file__).with_name("create_swgd_api_cases.py")
OUTPUT_PATH = ROOT / "SWGD-IMAP接口测试用例文档.docx"

NAVY = "17324D"
BLUE = "245A7A"
LIGHT_BLUE = "EAF2F7"
PALE_BLUE = "F5F9FB"
GREY = "66727C"
LIGHT_GREY = "F1F3F5"
BORDER = "B8C4CC"
WHITE = "FFFFFF"
RED = "B42318"
AMBER = "9A6700"
GREEN = "246B47"

FONT_CN = "微软雅黑"
FONT_MONO = "Consolas"


def load_case_module():
    spec = importlib.util.spec_from_file_location("swgd_case_definitions", CASE_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载用例定义: {CASE_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CASE_MODULE = load_case_module()


INTERFACES = [
    {
        "id": "FC-1.1",
        "service": "flow-center",
        "name": "保存流程日志",
        "method": "POST",
        "path": "/flowMessage/notify",
        "group": CASE_MODULE.FLOW_GROUP,
        "description": "保存业务处理流程日志，写入后返回日志主键及流水号。",
    },
    {
        "id": "FC-1.2",
        "service": "flow-center",
        "name": "按业务 ID 或流水号查询流程日志",
        "method": "POST",
        "path": "/flowMessage/queryLog",
        "group": CASE_MODULE.FLOW_GROUP,
        "description": "使用 bizId 或 serialNo 查询历史流程日志。",
    },
    {
        "id": "FC-2.1",
        "service": "flow-center",
        "name": "对外日志保存",
        "method": "POST",
        "path": "/flowApi/saveLogApi",
        "group": CASE_MODULE.FLOW_GROUP,
        "description": "保存外部系统调用产生的业务日志。",
    },
    {
        "id": "FC-2.2",
        "service": "flow-center",
        "name": "对外日志分页查询",
        "method": "POST",
        "path": "/flowApi/queryLogApi",
        "group": CASE_MODULE.FLOW_GROUP,
        "description": "按业务类型、时间范围、流水号、机构等条件分页查询。",
    },
    {
        "id": "FC-3.1",
        "service": "flow-center",
        "name": "日志保存，新增一条日志",
        "method": "POST",
        "path": "/optLog/saveLog",
        "group": CASE_MODULE.FLOW_GROUP,
        "description": "新增收单操作日志，返回持久化后的完整日志。",
    },
    {
        "id": "FC-3.2",
        "service": "flow-center",
        "name": "收单日志分页查询",
        "method": "POST",
        "path": "/optLog/querySwgdOrderReceiveLog",
        "group": CASE_MODULE.FLOW_GROUP,
        "description": "按流水号、状态、提单号、代理、日期等条件分页查询收单日志。",
    },
    {
        "id": "FC-3.3",
        "service": "flow-center",
        "name": "查询单个流程号的日志列表",
        "method": "POST",
        "path": "/optLog/getSwgdOrderReceiveLog",
        "group": CASE_MODULE.FLOW_GROUP,
        "description": "按单个流程号返回日志列表，不分页。",
    },
    {
        "id": "FC-3.5",
        "service": "flow-center",
        "name": "补充提单号",
        "method": "POST",
        "path": "/optLog/suppLementBillNo",
        "group": CASE_MODULE.FLOW_GROUP,
        "description": "为指定流程号补充或更新提单号。",
    },
    {
        "id": "MON-1.1",
        "service": "monitor",
        "name": "托管导入客户端目录监控",
        "method": "GET",
        "path": "/ftpMonitor/ftpMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "触发托管客户端目录扫描，属于有副作用的监控任务。",
    },
    {
        "id": "MON-1.2",
        "service": "monitor",
        "name": "查询 FTP 监控配置",
        "method": "POST",
        "path": "/ftpMonitor/queryFtpMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "按 FTP 地址分页查询 FTP_MONITOR 配置。",
    },
    {
        "id": "MON-1.3",
        "service": "monitor",
        "name": "新增或更新 FTP 监控配置",
        "method": "POST",
        "path": "/ftpMonitor/saveFtpMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "写入 FTP_MONITOR；无有效主键时执行新增，有主键时执行更新。",
    },
    {
        "id": "MON-1.4",
        "service": "monitor",
        "name": "按主键批量物理删除 FTP 配置",
        "method": "POST",
        "path": "/ftpMonitor/deleteFtpMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "按主键数组物理删除 FTP 监控配置。",
    },
    {
        "id": "MON-2.1",
        "service": "monitor",
        "name": "查询 SQL 监控配置",
        "method": "POST",
        "path": "/sqlMonitor/querySqlMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "按监控库和监控名称分页查询 SQL_MONITOR 配置。",
    },
    {
        "id": "MON-2.2",
        "service": "monitor",
        "name": "新增或更新 SQL 监控配置",
        "method": "POST",
        "path": "/sqlMonitor/saveSqlMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "写入 SQL_MONITOR，包含 SQL、阈值、比较符和告警邮件。",
    },
    {
        "id": "MON-2.3",
        "service": "monitor",
        "name": "按主键批量物理删除 SQL 配置",
        "method": "POST",
        "path": "/sqlMonitor/deleteSqlMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "按主键数组物理删除 SQL 监控配置。",
    },
    {
        "id": "MON-2.4",
        "service": "monitor",
        "name": "执行指定 SQL 监控配置",
        "method": "GET",
        "path": "/sqlMonitor/excuteSqlMonitor/{id}",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "执行指定 SQL，按阈值判断并可能发送告警邮件。",
    },
    {
        "id": "MON-3.1",
        "service": "monitor",
        "name": "用户余额监控",
        "method": "GET",
        "path": "/orderMonitor/userBalanceMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "检查用户余额，余额不为 0 时更新账单余额。",
    },
    {
        "id": "MON-4.1",
        "service": "monitor",
        "name": "计费记录与调用记录对比",
        "method": "GET",
        "path": "/chargeMonitor/recordCompareMonitor",
        "group": CASE_MODULE.MONITOR_GROUP,
        "description": "对比计费记录与调用记录，属于有副作用且历史偶发超时的任务。",
    },
]


EXTRA_CASES = [
    {
        "title": "CT-01 获取接口详情-有效主键",
        "case_id": "CT-01",
        "priority": "P1",
        "method": "POST",
        "url": "{{contentProtocol}}://{{contentHost}}:{{contentPort}}/{{contentContext}}/{{version}}/apiService/getDetailsById",
        "body": {"id": 21},
        "precondition": "content 服务可用，接口主键 21 存在。",
        "data": "id=21。",
        "expected": "HTTP 200，业务码 200，data.id=21，返回接口名称、URL、版本和数据示例。",
        "note": "截图中另一条 authCode=swgd_000015 的请求曾返回网关 404，建议以真实主键查询作为稳定冒烟数据。",
        "markers": ["api", "content", "smoke"],
    },
    {
        "title": "CT-02 按表头 ID 查询表体-有效主键",
        "case_id": "CT-02",
        "priority": "P1",
        "method": "POST",
        "url": "{{contentProtocol}}://{{contentHost}}:{{contentPort}}/{{contentContext}}/{{version}}/bodyFile/findBodyByHeadId",
        "body": {"headId": 63},
        "precondition": "content 服务可用，表头 ID 63 存在。",
        "data": "headId=63。",
        "expected": "HTTP 200，业务码 200，data 为数组，返回的记录均满足 headId=63。",
        "note": "该接口响应体约 2 KB，执行日志应限制响应记录长度以免淹没断言信息。",
        "markers": ["api", "content", "smoke"],
    },
]


SUPPLEMENTAL_INTERFACES = [
    {
        "id": "CT-1",
        "service": "content",
        "name": "获取接口详情",
        "method": "POST",
        "path": "/apiService/getDetailsById",
        "group": "content",
        "description": "按接口主键查询接口注册详情，截图中的快速验证条目之一。",
    },
    {
        "id": "CT-2",
        "service": "content",
        "name": "按表头 ID 查询表体",
        "method": "POST",
        "path": "/bodyFile/findBodyByHeadId",
        "group": "content",
        "description": "查询指定表头下的表体附件记录，截图中的快速验证条目之一。",
    },
]


def parse_description(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    labels = {
        "用例编号": "case_id",
        "优先级": "priority",
        "前置条件": "precondition",
        "测试数据": "data",
        "执行步骤": "steps",
        "预期结果": "expected",
        "注意": "note",
    }
    for line in text.splitlines():
        if "：" not in line:
            continue
        label, value = line.split("：", 1)
        key = labels.get(label.strip())
        if key:
            values[key] = value.strip()
    return values


def normalize_cases() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    main_cases: list[dict[str, Any]] = []
    for raw in CASE_MODULE.ALL_CASES:
        item = deepcopy(raw)
        item.update(parse_description(item["description"]))
        main_cases.append(item)
    return main_cases, deepcopy(EXTRA_CASES)


MAIN_CASES, EXTRA_CASES_NORMALIZED = normalize_cases()
ALL_DOC_CASES = MAIN_CASES + EXTRA_CASES_NORMALIZED
ALL_INTERFACES = INTERFACES + SUPPLEMENTAL_INTERFACES


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=90, bottom=80, end=90) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def keep_row_together(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def set_table_borders(table, color=BORDER, size="4") -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = f"w:{edge}"
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_font(run, size=None, bold=None, color=None, name=FONT_CN) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def style_paragraph(
    paragraph,
    *,
    size=9,
    bold=False,
    color="26323A",
    font=FONT_CN,
    before=0,
    after=3,
    line=1.15,
    align=None,
) -> None:
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = line
    if align is not None:
        paragraph.alignment = align
    for run in paragraph.runs:
        set_font(run, size=size, bold=bold, color=color, name=font)


def add_text(
    paragraph,
    text: str,
    *,
    size=9,
    bold=False,
    color="26323A",
    font=FONT_CN,
) -> Any:
    run = paragraph.add_run(text)
    set_font(run, size=size, bold=bold, color=color, name=font)
    return run


def set_cell_text(
    cell,
    text: str,
    *,
    size=8.5,
    bold=False,
    color="26323A",
    font=FONT_CN,
    align=WD_ALIGN_PARAGRAPH.LEFT,
) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.08
    add_text(paragraph, text, size=size, bold=bold, color=color, font=font)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    set_cell_margins(cell)


def set_cell_multiline(
    cell,
    lines: list[tuple[str, dict[str, Any]]],
    *,
    align=WD_ALIGN_PARAGRAPH.LEFT,
) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.05
    for index, (text, options) in enumerate(lines):
        if index:
            paragraph.add_run().add_break()
        add_text(paragraph, text, **options)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    set_cell_margins(cell)


def set_column_widths(table, widths_cm: list[float]) -> None:
    for row in table.rows:
        for index, width in enumerate(widths_cm):
            row.cells[index].width = Cm(width)
    grid = table._tbl.tblGrid
    for index, width in enumerate(widths_cm):
        grid.gridCol_lst[index].w = Cm(width)


def add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    add_text(paragraph, "第 ", size=8, color=GREY)
    run = paragraph.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char1)
    run._r.append(instr_text)
    run._r.append(fld_char2)
    set_font(run, size=8, color=GREY)
    add_text(paragraph, " 页", size=8, color=GREY)


def setup_document(document: Document) -> None:
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Cm(29.7)
    section.page_height = Cm(21)
    section.top_margin = Cm(1.35)
    section.bottom_margin = Cm(1.25)
    section.left_margin = Cm(1.45)
    section.right_margin = Cm(1.45)
    section.header_distance = Cm(0.55)
    section.footer_distance = Cm(0.5)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = FONT_CN
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    normal.font.size = Pt(9)
    normal.font.color.rgb = RGBColor.from_string("26323A")
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.15

    for style_name, size, color in (
        ("Title", 28, NAVY),
        ("Heading 1", 16, NAVY),
        ("Heading 2", 12.5, BLUE),
        ("Heading 3", 10.5, BLUE),
    ):
        style = styles[style_name]
        style.font.name = FONT_CN
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(color)
        style.font.bold = True
        style.paragraph_format.space_before = Pt(8)
        style.paragraph_format.space_after = Pt(4)

    properties = document.core_properties
    properties.title = "SWGD IMAP 接口测试用例文档"
    properties.subject = "swgd-imap-flow-center 与 swgd-imap-monitor 接口测试"
    properties.author = "AIRETEST"
    properties.keywords = "SWGD, IMAP, API, 接口测试, 测试用例"
    properties.comments = "基于接口截图、已导入请求定义及只读探测结果生成。"

    header = section.header
    header_table = header.add_table(rows=1, cols=2, width=Cm(26.8))
    header_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    header_table.autofit = False
    set_column_widths(header_table, [21.8, 5.0])
    set_cell_text(
        header_table.cell(0, 0),
        "SWGD IMAP 接口测试用例文档",
        size=8,
        bold=True,
        color=BLUE,
    )
    set_cell_text(
        header_table.cell(0, 1),
        "版本 V1.0",
        size=8,
        color=GREY,
        align=WD_ALIGN_PARAGRAPH.RIGHT,
    )
    for cell in header_table.rows[0].cells:
        set_cell_shading(cell, WHITE)
    set_table_borders(header_table, color=WHITE, size="0")

    footer = section.footer
    footer_paragraph = footer.paragraphs[0]
    footer_paragraph.paragraph_format.space_before = Pt(0)
    footer_paragraph.paragraph_format.space_after = Pt(0)
    add_text(footer_paragraph, "AIRETEST · 接口测试基线", size=8, color=GREY)
    add_page_number(footer_paragraph)


def add_cover(document: Document) -> None:
    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(50)

    eyebrow = document.add_paragraph()
    eyebrow.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(eyebrow, "API TEST CASE SPECIFICATION", size=10, bold=True, color=BLUE)

    title = document.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(8)
    title.paragraph_format.space_after = Pt(10)
    add_text(
        title,
        "SWGD IMAP 接口测试用例文档",
        size=28,
        bold=True,
        color=NAVY,
    )

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(34)
    add_text(
        subtitle,
        "swgd-imap-flow-center / swgd-imap-monitor / content 快速验证",
        size=12,
        color=GREY,
    )

    metadata = [
        ("文档版本", "V1.0"),
        ("编制日期", date(2026, 11, 11).strftime("%Y-%m-%d")),
        ("覆盖接口", f"{len(ALL_INTERFACES)} 个请求条目"),
        ("测试用例", f"{len(ALL_DOC_CASES)} 条"),
        ("适用范围", "开发自测、测试准入、回归执行"),
        ("文档状态", "评审版"),
    ]
    table = document.add_table(rows=4, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_column_widths(table, [4.0, 6.2, 4.0, 6.2])
    set_table_borders(table, color=BORDER, size="4")
    for index, (label, value) in enumerate(metadata):
        row, col = divmod(index, 2)
        left_cell = table.cell(row, col * 2)
        right_cell = table.cell(row, col * 2 + 1)
        set_cell_text(left_cell, label, size=9, bold=True, color=NAVY)
        set_cell_text(right_cell, value, size=9)
        set_cell_shading(left_cell, LIGHT_BLUE)
        set_cell_shading(right_cell, WHITE)
        keep_row_together(table.rows[row])

    note = document.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note.paragraph_format.space_before = Pt(28)
    add_text(
        note,
        "本文档以接口请求定义、已导入用例和只读探测结果为依据；副作用接口需在测试窗口内执行。",
        size=8.5,
        color=GREY,
    )
    document.add_page_break()


def add_heading(document: Document, text: str, level: int = 1) -> None:
    paragraph = document.add_heading(level=level)
    add_text(paragraph, text, size={1: 16, 2: 12.5, 3: 10.5}[level], bold=True, color=NAVY if level == 1 else BLUE)
    paragraph.paragraph_format.keep_with_next = True


def add_body_paragraph(
    document: Document,
    text: str,
    *,
    bold_prefix: str | None = None,
    after=4,
) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = 1.2
    if bold_prefix and text.startswith(bold_prefix):
        add_text(paragraph, bold_prefix, size=9, bold=True, color=NAVY)
        add_text(paragraph, text[len(bold_prefix):], size=9)
    else:
        add_text(paragraph, text, size=9)


def add_bullets(document: Document, items: list[str]) -> None:
    for item in items:
        paragraph = document.add_paragraph(style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.paragraph_format.line_spacing = 1.12
        add_text(paragraph, item, size=8.8)


def add_overview(document: Document) -> None:
    add_heading(document, "1. 文档概述")
    add_body_paragraph(
        document,
        "本文件覆盖截图中的 20 个请求条目，其中 18 个为编号业务接口，2 个为同一 flow-center 分组下的 content 快速验证接口。用例设计同时参考当前项目中的请求 URL、请求体、历史响应及只读探测结果。",
    )
    add_heading(document, "1.1 测试目标", level=2)
    add_bullets(
        document,
        [
            "验证接口可用性、响应结构、核心业务字段及分页返回是否符合约定。",
            "覆盖正常、空结果、关键参数缺失、空数组、不存在主键等主要异常与边界场景。",
            "明确写操作、物理删除、SQL 执行、目录扫描、余额更新等接口的副作用和执行限制。",
            "为后续自动化回归提供稳定的用例编号、测试数据和字段级断言基线。",
        ],
    )
    add_heading(document, "1.2 覆盖范围", level=2)
    add_bullets(
        document,
        [
            "swgd-imap-flow-center：流程日志保存、查询、分页、单流程号查询和补充提单号。",
            "swgd-imap-monitor：FTP 目录监控、FTP 配置、SQL 配置、SQL 执行、余额监控和计费对比。",
            "content 快速验证：按接口主键获取详情、按表头 ID 查找表体记录。",
            "不包含性能容量、安全渗透、真实邮件送达和长期稳定性测试。",
        ],
    )
    add_heading(document, "1.3 用例统计", level=2)
    summary_table = document.add_table(rows=1, cols=5)
    summary_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    summary_table.autofit = False
    set_column_widths(summary_table, [4.2, 4.2, 4.2, 4.2, 5.2])
    headers = ["测试服务", "接口条目", "测试用例", "自动化断言", "执行说明"]
    for index, text in enumerate(headers):
        cell = summary_table.cell(0, index)
        set_cell_text(cell, text, size=8.5, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(cell, NAVY)
    set_repeat_table_header(summary_table.rows[0])
    rows = [
        (
            "flow-center",
            "8",
            str(len([c for c in MAIN_CASES if c["group_path"] == CASE_MODULE.FLOW_GROUP])),
            "HTTP + code/message + data 结构",
            "其中 4 条为日志写操作",
        ),
        (
            "monitor",
            "10",
            str(len([c for c in MAIN_CASES if c["group_path"] == CASE_MODULE.MONITOR_GROUP])),
            "分页字段、空结果、错误码",
            "6 条具有真实副作用",
        ),
        (
            "content",
            "2",
            str(len(EXTRA_CASES_NORMALIZED)),
            "HTTP + code + 核心 data 字段",
            "快速验证，仅使用稳定主键",
        ),
        (
            "合计",
            str(len(ALL_INTERFACES)),
            str(len(ALL_DOC_CASES)),
            f"{len(ALL_DOC_CASES)} 组用例断言",
            "按风险分级执行",
        ),
    ]
    for row_index, values in enumerate(rows, start=1):
        row = summary_table.add_row()
        keep_row_together(row)
        for col_index, text in enumerate(values):
            cell = row.cells[col_index]
            set_cell_text(
                cell,
                text,
                size=8.5,
                bold=row_index == len(rows),
                align=WD_ALIGN_PARAGRAPH.CENTER if col_index < 4 else WD_ALIGN_PARAGRAPH.LEFT,
            )
            set_cell_shading(cell, LIGHT_GREY if row_index == len(rows) else (PALE_BLUE if row_index % 2 == 0 else WHITE))
    set_table_borders(summary_table)


def add_environment(document: Document) -> None:
    document.add_page_break()
    add_heading(document, "2. 测试环境与执行约定")
    add_heading(document, "2.1 环境变量", level=2)
    table = document.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_column_widths(table, [4.0, 7.2, 10.0, 5.4])
    for index, text in enumerate(["变量/请求头", "建议值", "用途", "安全要求"]):
        cell = table.cell(0, index)
        set_cell_text(cell, text, size=8.5, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(cell, NAVY)
    set_repeat_table_header(table.rows[0])
    rows = [
        ("baseUrl", "http://<flow-center-host>:<port>/swgdimapgateway", "flow-center 请求前缀", "按环境覆盖"),
        ("mbaseUrl", "http://<monitor-host>:<port>", "monitor 请求前缀", "按环境覆盖"),
        ("contentProtocol", "http", "content 协议", "按环境覆盖"),
        ("contentHost / contentPort", "按实际网关配置", "content 主机与端口", "禁止提交真实生产值"),
        ("contentContext / version", "/swgdimapgateway/swgd-imap-content / v1", "content 上下文和版本", "按环境覆盖"),
        ("epToken", "从测试环境变量池注入", "统一鉴权请求头", "不得写入文档或日志"),
        ("Content-Type", "application/json", "JSON 请求头", "无"),
    ]
    for row_index, values in enumerate(rows, start=1):
        row = table.add_row()
        keep_row_together(row)
        for col_index, text in enumerate(values):
            cell = row.cells[col_index]
            set_cell_text(cell, text, size=8, bold=col_index == 0)
            set_cell_shading(cell, PALE_BLUE if row_index % 2 == 0 else WHITE)
    set_table_borders(table)

    add_heading(document, "2.2 统一断言", level=2)
    add_bullets(
        document,
        [
            "所有接口先断言 HTTP 状态码为 200；业务成功以响应体 code=200、message=Success 为准。",
            "分页接口同时断言 data.total 为数字、data.rows 为数组；空结果场景额外断言 total=0。",
            "参数错误或业务失败通常仍返回 HTTP 200，因此必须断言响应体 code 非 200，不能只看 HTTP 状态。",
            "字符串型但全为数字的流水号，应在期望值中保留 JSON 引号，避免断言引擎按数字解析。",
            "目录扫描、余额监控、计费对比等接口可能返回空字符串，稳定基线先断言 HTTP 200，再补充响应耗时和业务日志检查。",
        ],
    )

    add_heading(document, "2.3 数据与清理", level=2)
    add_bullets(
        document,
        [
            "新增 FTP 配置使用 TEST-NET 地址 192.0.2.10，记录主键后通过批量删除接口清理。",
            "新增 SQL 配置使用 qa@example.invalid，禁止向真实收件人发送告警邮件，并在执行后物理删除。",
            "删除接口的破坏性正例应使用专用测试数据；当前基线使用不存在的主键 987654321 验证无数据影响。",
            "日志写入用例执行后应记录新增主键；若目标环境没有删除接口，执行前必须准备数据库级清理方案。",
        ],
    )


def add_coverage_matrix(document: Document) -> None:
    document.add_page_break()
    add_heading(document, "3. 接口覆盖矩阵")
    add_body_paragraph(
        document,
        "接口顺序沿用截图。方法以当前导入的请求定义和实际可执行请求为准；截图中个别方法标签不清晰，不以颜色或字号推断。",
    )
    table = document.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_column_widths(table, [2.0, 6.3, 2.0, 8.0, 2.2, 6.2])
    headers = ["编号", "接口名称", "方法", "路径", "用例数", "关键风险"]
    for index, text in enumerate(headers):
        cell = table.cell(0, index)
        set_cell_text(cell, text, size=8.5, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(cell, NAVY)
    set_repeat_table_header(table.rows[0])
    for row_index, interface in enumerate(ALL_INTERFACES, start=1):
        cases = [c for c in ALL_DOC_CASES if case_belongs_to_interface(c, interface)]
        risk = "写操作" if any("write" in c.get("markers", []) for c in cases) else "低"
        if any("side-effect" in c.get("markers", []) for c in cases):
            risk = "副作用"
        if interface["service"] == "content":
            risk = "依赖有效主键"
        row = table.add_row()
        keep_row_together(row)
        values = [
            interface["id"],
            interface["name"],
            interface["method"],
            interface["path"],
            str(len(cases)),
            risk,
        ]
        for col_index, text in enumerate(values):
            cell = row.cells[col_index]
            set_cell_text(
                cell,
                text,
                size=7.8,
                bold=col_index in (0, 2),
                color=RED if risk == "副作用" and col_index == 5 else "26323A",
                font=FONT_MONO if col_index in (2, 3) else FONT_CN,
                align=WD_ALIGN_PARAGRAPH.CENTER if col_index in (0, 2, 4) else WD_ALIGN_PARAGRAPH.LEFT,
            )
            set_cell_shading(cell, PALE_BLUE if row_index % 2 == 0 else WHITE)
    set_table_borders(table)


def path_matches(url: str, path: str) -> bool:
    if path.endswith("/{id}"):
        return path.removesuffix("/{id}") + "/" in url
    return path in url


def case_belongs_to_interface(case: dict[str, Any], interface: dict[str, Any]) -> bool:
    url = case["url"]
    if interface["service"] == "content":
        return path_matches(url, interface["path"])
    if interface["service"] == "flow-center":
        return case.get("group_path") == CASE_MODULE.FLOW_GROUP and path_matches(
            url, interface["path"]
        )
    if interface["service"] == "monitor":
        return case.get("group_path") == CASE_MODULE.MONITOR_GROUP and path_matches(
            url, interface["path"]
        )
    return False


def format_json_body(body: Any) -> str:
    if body is None:
        return "无请求体"
    if body == {}:
        return "{}"
    return json.dumps(body, ensure_ascii=False, indent=2)


def execution_tags(case: dict[str, Any]) -> str:
    markers = set(case.get("markers") or [])
    tags: list[str] = []
    if "side-effect" in markers:
        tags.append("副作用")
    elif "write" in markers:
        tags.append("写操作")
    else:
        tags.append("只读")
    if "smoke" in markers:
        tags.append("冒烟")
    if "negative" in markers:
        tags.append("异常")
    if "boundary" in markers:
        tags.append("边界")
    return " / ".join(tags)


def add_request_cell(cell, case: dict[str, Any]) -> None:
    body_text = format_json_body(case.get("body"))
    lines: list[tuple[str, dict[str, Any]]] = [
        (
            f"{case['method']} {short_path(case['url'])}",
            {"size": 7.4, "bold": True, "color": BLUE, "font": FONT_MONO},
        )
    ]
    for line in body_text.splitlines():
        lines.append(
            (
                line,
                {"size": 7.1, "color": "35424B", "font": FONT_MONO},
            )
        )
    set_cell_multiline(cell, lines)


def short_path(url: str) -> str:
    result = re.sub(r"^\{\{(baseUrl|mbaseUrl)\}\}", "", url)
    if result.startswith("{{contentProtocol}}"):
        return "/{{contentContext}}/{{version}}" + result.split("/{{version}}", 1)[-1]
    return result


def add_issue_table(document: Document) -> None:
    document.add_page_break()
    add_heading(document, "6. 本次验证发现与风险")
    add_body_paragraph(
        document,
        "以下结论来自 2026-11-11 的只读探测和安全场景执行。失败用例保留正确业务预期，不通过修改预期来掩盖接口行为。",
    )
    table = document.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_column_widths(table, [2.0, 4.4, 5.0, 6.6, 5.2, 3.4])
    headers = ["编号", "关联用例", "问题", "实际结果", "预期结果/影响", "建议"]
    for index, text in enumerate(headers):
        cell = table.cell(0, index)
        set_cell_text(cell, text, size=8.3, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(cell, RED)
    set_repeat_table_header(table.rows[0])
    rows = [
        (
            "DEF-01",
            "FC-07",
            "对外日志保存未校验空请求体",
            "HTTP 200、code=200，并写入空日志主键 1971。",
            "应返回业务错误且不写库；当前会污染日志表。",
            "补充必填字段校验；清理测试环境主键 1971。",
        ),
        (
            "DEF-02",
            "FC-12",
            "收单日志保存未校验空请求体",
            "HTTP 200、code=200，并写入空日志主键 1973。",
            "应返回业务错误且不写库；当前会污染日志表。",
            "复用统一参数校验；清理测试环境主键 1973。",
        ),
        (
            "DEF-03",
            "FC-18",
            "单流程号查询缺少 serialNo 时未拒绝",
            "HTTP 200、code=200，返回全部日志列表。",
            "应提示流水号缺失，避免意外全表查询。",
            "服务端增加必填校验并限制无条件查询。",
        ),
        (
            "RISK-01",
            "MON-4.1",
            "计费对比接口曾出现读超时",
            "历史执行存在 ReadTimeout，也有成功记录。",
            "常规超时阈值会产生误报。",
            "单独设置较长超时并记录耗时分布。",
        ),
        (
            "RISK-02",
            "MON-1.1 / MON-3.1",
            "目录扫描和余额更新直接产生业务变更",
            "返回体可能为空字符串，无法只靠响应判断内部结果。",
            "误执行会影响真实目录、账单或余额数据。",
            "仅使用专用测试窗口和可回滚数据，并检查任务日志。",
        ),
    ]
    for row_index, values in enumerate(rows, start=1):
        row = table.add_row()
        keep_row_together(row)
        for col_index, text in enumerate(values):
            cell = row.cells[col_index]
            set_cell_text(
                cell,
                text,
                size=7.8,
                bold=col_index == 0,
                color=RED if col_index == 0 else "26323A",
            )
            set_cell_shading(cell, "FFF2F0" if row_index <= 3 else PALE_BLUE)
    set_table_borders(table)


def add_execution_plan(document: Document) -> None:
    add_heading(document, "7. 建议执行顺序")
    table = document.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_column_widths(table, [2.0, 7.0, 8.5, 9.1])
    for index, text in enumerate(["批次", "范围", "执行内容", "准出条件"]):
        cell = table.cell(0, index)
        set_cell_text(cell, text, size=8.5, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(cell, NAVY)
    set_repeat_table_header(table.rows[0])
    rows = [
        ("P0-1", "只读查询与缺参用例", "FC-03、FC-04、FC-08、FC-13、FC-16、MON-1.2、MON-2.1", "成功码、分页结构和主要错误码通过"),
        ("P0-2", "写操作", "FC-01、FC-06、FC-11、FC-19、MON-1.3、MON-2.2", "写后查询可验证，测试数据已登记"),
        ("P1", "副作用任务", "MON-1.1、MON-2.4、MON-3.1、MON-4.1", "任务耗时、内部日志和业务结果均可核对"),
        ("清理", "删除与临时数据", "删除测试 FTP/SQL 配置，清理新增日志", "无遗留临时数据，告警邮箱未向真实用户发送"),
    ]
    for row_index, values in enumerate(rows, start=1):
        row = table.add_row()
        keep_row_together(row)
        for col_index, text in enumerate(values):
            cell = row.cells[col_index]
            set_cell_text(cell, text, size=8, bold=col_index == 0)
            set_cell_shading(cell, PALE_BLUE if row_index % 2 == 0 else WHITE)
    set_table_borders(table)


def add_detailed_cases(document: Document) -> None:
    document.add_page_break()
    add_heading(document, "4. 详细测试用例")
    add_body_paragraph(
        document,
        "每条用例只针对一个接口场景。请求头统一携带 Content-Type 和 epToken；表中请求体为实际发送内容，变量在执行前由环境或工作空间变量替换。",
    )
    current_service = None
    for interface in ALL_INTERFACES:
        if interface["service"] != current_service:
            current_service = interface["service"]
            service_title = {
                "flow-center": "4.1 swgd-imap-flow-center",
                "monitor": "4.2 swgd-imap-monitor",
                "content": "4.3 content 快速验证",
            }[current_service]
            add_heading(document, service_title, level=2)
        add_heading(
            document,
            f"{interface['id']} {interface['name']}",
            level=3,
        )
        metadata = document.add_paragraph()
        metadata.paragraph_format.space_before = Pt(0)
        metadata.paragraph_format.space_after = Pt(4)
        add_text(metadata, interface["description"], size=8.7, color=GREY)
        endpoint = document.add_paragraph()
        endpoint.paragraph_format.space_after = Pt(5)
        add_text(endpoint, f"{interface['method']}  ", size=8.2, bold=True, color=BLUE, font=FONT_MONO)
        add_text(endpoint, interface["path"], size=8.2, color="35424B", font=FONT_MONO)

        cases = [c for c in ALL_DOC_CASES if case_belongs_to_interface(c, interface)]
        if not cases:
            raise RuntimeError(f"接口没有对应用例: {interface['id']}")
        table = document.add_table(rows=1, cols=6)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        set_column_widths(table, [2.2, 4.0, 5.4, 8.1, 5.4, 1.7])
        headers = ["用例/优先级", "测试场景", "前置条件与数据", "请求体", "预期结果", "类型"]
        for index, text in enumerate(headers):
            cell = table.cell(0, index)
            set_cell_text(cell, text, size=8.2, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER)
            set_cell_shading(cell, NAVY)
        set_repeat_table_header(table.rows[0])
        for case_index, case in enumerate(cases, start=1):
            row = table.add_row()
            keep_row_together(row)
            priority = case.get("priority", "P1")
            priority_color = RED if priority == "P0" else (AMBER if priority == "P1" else GREEN)
            set_cell_multiline(
                row.cells[0],
                [
                    (
                        case.get("case_id") or case["title"].split()[0],
                        {"size": 8.0, "bold": True, "color": NAVY, "font": FONT_MONO},
                    ),
                    (priority, {"size": 8.0, "bold": True, "color": priority_color}),
                ],
                align=WD_ALIGN_PARAGRAPH.CENTER,
            )
            scenario = re.sub(r"^(FC|IM|CT)-\d+\s*", "", case["title"])
            set_cell_text(row.cells[1], scenario, size=8.2, bold=True)
            precondition = case.get("precondition", "")
            data = case.get("data", "")
            set_cell_multiline(
                row.cells[2],
                [
                    ("前置：", {"size": 7.8, "bold": True, "color": BLUE}),
                    (precondition, {"size": 7.7}),
                    ("数据：", {"size": 7.8, "bold": True, "color": BLUE}),
                    (data, {"size": 7.7}),
                ],
            )
            add_request_cell(row.cells[3], case)
            expected = case.get("expected", "")
            note = case.get("note", "")
            expected_lines: list[tuple[str, dict[str, Any]]] = [
                (expected, {"size": 7.8}),
            ]
            if note:
                expected_lines.extend(
                    [
                        ("备注：", {"size": 7.4, "bold": True, "color": AMBER}),
                        (note, {"size": 7.3, "color": GREY}),
                    ]
                )
            set_cell_multiline(row.cells[4], expected_lines)
            tags = execution_tags(case)
            set_cell_text(
                row.cells[5],
                tags,
                size=7.3,
                bold="副作用" in tags,
                color=RED if "副作用" in tags else "35424B",
                align=WD_ALIGN_PARAGRAPH.CENTER,
            )
            for col_index, cell in enumerate(row.cells):
                if col_index == 5 and "副作用" in tags:
                    set_cell_shading(cell, "FFF2F0")
                elif case_index % 2 == 0:
                    set_cell_shading(cell, PALE_BLUE)
        set_table_borders(table)


def add_appendix(document: Document) -> None:
    document.add_page_break()
    add_heading(document, "8. 附录")
    add_heading(document, "8.1 用例编号规则", level=2)
    table = document.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_column_widths(table, [4.2, 7.0, 15.4])
    for index, text in enumerate(["前缀", "所属范围", "说明"]):
        cell = table.cell(0, index)
        set_cell_text(cell, text, size=8.5, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(cell, NAVY)
    for row_index, values in enumerate(
        [
            ("FC-xx", "flow-center", "流程日志、对外日志、收单日志及提单号"),
            ("IM-xx", "monitor", "FTP、SQL、余额与计费监控"),
            ("CT-xx", "content", "截图中同组附加的快速验证接口"),
        ],
        start=1,
    ):
        row = table.add_row()
        for col_index, text in enumerate(values):
            cell = row.cells[col_index]
            set_cell_text(cell, text, size=8.2, font=FONT_MONO if col_index == 0 else FONT_CN)
            set_cell_shading(cell, PALE_BLUE if row_index % 2 == 0 else WHITE)
    set_table_borders(table)

    add_heading(document, "8.2 请求模板说明", level=2)
    add_bullets(
        document,
        [
            "flow-center 用例使用 {{baseUrl}} + 业务路径；实际执行前需确保 baseUrl 已包含网关上下文。",
            "monitor 用例使用 {{mbaseUrl}}；该变量属于全局变量，不依赖单个项目。",
            "content 快速验证使用 protocol、host、port、context、version 五段变量拼接，避免将环境地址固化在文档中。",
            "所有 POST 请求使用 application/json；所有请求携带 epToken，但文档中不记录实际令牌。",
        ],
    )

    add_heading(document, "8.3 评审检查项", level=2)
    check_table = document.add_table(rows=1, cols=4)
    check_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    check_table.autofit = False
    set_column_widths(check_table, [2.0, 10.8, 3.0, 10.8])
    for index, text in enumerate(["序号", "检查项", "状态", "负责人/备注"]):
        cell = check_table.cell(0, index)
        set_cell_text(cell, text, size=8.5, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(cell, NAVY)
    checks = [
        "接口路径和请求方法与当前环境一致",
        "测试数据在目标环境存在且可清理",
        "副作用接口已获得执行窗口和回滚方案",
        "新增失败用例已登记缺陷或风险",
        "epToken 和真实地址未写入文档正文",
        "执行结果已归档并可追溯到用例编号",
    ]
    for row_index, text in enumerate(checks, start=1):
        row = check_table.add_row()
        values = [str(row_index), text, "□", ""]
        for col_index, value in enumerate(values):
            cell = row.cells[col_index]
            set_cell_text(cell, value, size=8.2)
            if row_index % 2 == 0:
                set_cell_shading(cell, PALE_BLUE)
    set_table_borders(check_table)


def validate_document_data() -> None:
    expected_count = len(CASE_MODULE.ALL_CASES) + len(EXTRA_CASES)
    if expected_count != len(ALL_DOC_CASES):
        raise RuntimeError("用例总数与定义不一致")
    interface_ids = [item["id"] for item in ALL_INTERFACES]
    if len(interface_ids) != len(set(interface_ids)):
        raise RuntimeError("接口编号重复")
    service_counts = {
        service: len([item for item in ALL_INTERFACES if item["service"] == service])
        for service in ("flow-center", "monitor", "content")
    }
    if service_counts != {"flow-center": 8, "monitor": 10, "content": 2}:
        raise RuntimeError(f"接口覆盖数量异常: {service_counts}")

    covered_titles: set[str] = set()
    for interface in ALL_INTERFACES:
        cases = [c for c in ALL_DOC_CASES if case_belongs_to_interface(c, interface)]
        if not cases:
            raise RuntimeError(f"接口未覆盖: {interface['id']}")
        for case in cases:
            if case["title"] in covered_titles:
                raise RuntimeError(f"用例被重复分配: {case['title']}")
            covered_titles.add(case["title"])
    if len(covered_titles) != len(ALL_DOC_CASES):
        missing = {c["title"] for c in ALL_DOC_CASES} - covered_titles
        raise RuntimeError(f"未分配用例: {sorted(missing)}")


def validate_saved_document(path: Path) -> None:
    document = Document(path)
    full_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    table_text = "\n".join(
        cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    )
    combined = full_text + "\n" + table_text
    missing = [case["case_id"] for case in ALL_DOC_CASES if case["case_id"] not in combined]
    if missing:
        raise RuntimeError(f"文档缺少用例编号: {missing}")
    if "SWGD IMAP 接口测试用例文档" not in combined:
        raise RuntimeError("文档标题缺失")
    if "本次验证发现与风险" not in combined:
        raise RuntimeError("风险章节缺失")
    if len(document.tables) < 20:
        raise RuntimeError(f"表格数量异常: {len(document.tables)}")
    if path.stat().st_size < 20_000:
        raise RuntimeError(f"文档文件异常偏小: {path.stat().st_size}")


def main() -> int:
    validate_document_data()
    document = Document()
    setup_document(document)
    add_cover(document)
    add_overview(document)
    add_environment(document)
    add_coverage_matrix(document)
    add_detailed_cases(document)
    add_issue_table(document)
    add_execution_plan(document)
    add_appendix(document)
    document.save(OUTPUT_PATH)
    validate_saved_document(OUTPUT_PATH)

    print(f"OUTPUT={OUTPUT_PATH}")
    print(f"INTERFACES={len(ALL_INTERFACES)}")
    print(f"CASES={len(ALL_DOC_CASES)}")
    print(f"TABLES={len(document.tables)}")
    print(f"BYTES={OUTPUT_PATH.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
