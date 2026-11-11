#!/usr/bin/env python3
"""Export the SWGD IMAP API test cases to an Excel-friendly UTF-8 CSV."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DOC_MODULE_PATH = Path(__file__).with_name("generate_swgd_api_test_case_doc.py")
OUTPUT_PATH = ROOT / "SWGD-IMAP接口测试用例.csv"

FIELDS = [
    "用例编号",
    "用例标题",
    "所属服务",
    "接口编号",
    "接口名称",
    "优先级",
    "请求方法",
    "请求URL",
    "请求头(JSON)",
    "请求体(JSON)",
    "前置条件",
    "测试数据",
    "执行步骤",
    "预期结果",
    "断言规则(JSON)",
    "用例类型",
    "是否副作用",
    "是否自动化",
    "备注",
]


def load_doc_module():
    spec = importlib.util.spec_from_file_location("swgd_doc_definitions", DOC_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载文档用例定义: {DOC_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DOC = load_doc_module()


WRITE_INTERFACES = {
    "FC-1.1",
    "FC-2.1",
    "FC-3.1",
    "FC-3.5",
    "MON-1.3",
    "MON-1.4",
    "MON-2.2",
    "MON-2.3",
}
SIDE_EFFECT_INTERFACES = {
    "MON-1.1",
    "MON-1.3",
    "MON-1.4",
    "MON-2.2",
    "MON-2.3",
    "MON-2.4",
    "MON-3.1",
    "MON-4.1",
}

OBSERVED_NOTES = {
    "FC-07": (
        "2026-11-11 验证：空请求体仍返回 code=200，并写入空日志 ID 1971；"
        "本用例保留失败预期。"
    ),
    "FC-12": (
        "2026-11-11 验证：空请求体仍返回 code=200，并写入空日志 ID 1973；"
        "本用例保留失败预期。"
    ),
    "FC-18": (
        "2026-11-11 验证：缺少 serialNo 时返回全部日志；本用例保留失败预期。"
    ),
}


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def flat_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", "\n").splitlines()).strip()


def interface_for_case(case: dict[str, Any]) -> dict[str, Any]:
    matches = [
        interface
        for interface in DOC.ALL_INTERFACES
        if DOC.case_belongs_to_interface(case, interface)
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"用例应且只应匹配一个接口: {case['title']} -> {[item['id'] for item in matches]}"
        )
    return matches[0]


def default_assertions(case: dict[str, Any]) -> list[dict[str, Any]]:
    common = [
        {
            "assertion_type": "status_code",
            "expression": None,
            "operator": "eq",
            "expected": "200",
            "priority": "P0",
            "order": 0,
        },
        {
            "assertion_type": "json_path",
            "expression": "$.code",
            "operator": "eq",
            "expected": "200",
            "priority": "P0",
            "order": 1,
        },
    ]
    if case["case_id"] == "CT-01":
        common.append(
            {
                "assertion_type": "json_path",
                "expression": "$.data.id",
                "operator": "eq",
                "expected": "21",
                "priority": "P1",
                "order": 2,
            }
        )
    elif case["case_id"] == "CT-02":
        common.append(
            {
                "assertion_type": "json_path",
                "expression": "$.data[0].headId",
                "operator": "eq",
                "expected": "63",
                "priority": "P1",
                "order": 2,
            }
        )
    return common


def execution_type(case: dict[str, Any], interface: dict[str, Any]) -> str:
    tags = [tag for tag in DOC.execution_tags(case).split(" / ") if tag != "只读"]
    if interface["id"] in WRITE_INTERFACES:
        tags.insert(0, "写操作")
    if interface["id"] in SIDE_EFFECT_INTERFACES and "副作用" not in tags:
        tags.insert(0, "副作用")
    if not tags:
        tags.append("只读")
    return "/".join(dict.fromkeys(tags))


def side_effect(interface: dict[str, Any]) -> str:
    risky_interfaces = WRITE_INTERFACES | SIDE_EFFECT_INTERFACES
    return "是" if interface["id"] in risky_interfaces else "否"


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for case in DOC.ALL_DOC_CASES:
        interface = interface_for_case(case)
        assertions = case.get("assertions") or default_assertions(case)
        note_parts = [
            flat_text(case.get("note")),
            OBSERVED_NOTES.get(case.get("case_id", ""), ""),
        ]
        rows.append(
            {
                "用例编号": case["case_id"],
                "用例标题": flat_text(case["title"]),
                "所属服务": interface["service"],
                "接口编号": interface["id"],
                "接口名称": interface["name"],
                "优先级": case["priority"],
                "请求方法": case["method"],
                "请求URL": flat_text(case["url"]),
                "请求头(JSON)": compact_json(case.get("headers") or {}),
                "请求体(JSON)": (
                    compact_json(case["body"]) if case.get("body") is not None else "无"
                ),
                "前置条件": flat_text(case.get("precondition")),
                "测试数据": flat_text(case.get("data")),
                "执行步骤": flat_text(
                    "1.准备并核对前置数据；2.替换环境变量后发送请求；"
                    "3.检查HTTP状态、业务码和响应字段；4.记录结果并按需清理。"
                ),
                "预期结果": flat_text(case.get("expected")),
                "断言规则(JSON)": compact_json(assertions),
                "用例类型": execution_type(case, interface),
                "是否副作用": side_effect(interface),
                "是否自动化": "是",
                "备注": " ".join(part for part in note_parts if part).strip(),
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=FIELDS,
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def validate_csv(expected_rows: list[dict[str, str]]) -> None:
    with OUTPUT_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise RuntimeError(f"CSV 表头异常: {reader.fieldnames}")
        rows = list(reader)

    if len(rows) != 39 or len(rows) != len(expected_rows):
        raise RuntimeError(f"CSV 行数异常: {len(rows)}")
    case_ids = [row["用例编号"] for row in rows]
    if len(case_ids) != len(set(case_ids)):
        raise RuntimeError("CSV 用例编号重复")
    if case_ids != [case["case_id"] for case in DOC.ALL_DOC_CASES]:
        raise RuntimeError("CSV 用例顺序与定义不一致")

    required = [
        "用例编号",
        "用例标题",
        "接口编号",
        "请求方法",
        "请求URL",
        "预期结果",
        "断言规则(JSON)",
    ]
    for row in rows:
        missing = [field for field in required if not row[field].strip()]
        if missing:
            raise RuntimeError(f"{row['用例编号']} 缺少字段: {missing}")
        json.loads(row["请求头(JSON)"])
        if row["请求体(JSON)"] != "无":
            json.loads(row["请求体(JSON)"])
        assertions = json.loads(row["断言规则(JSON)"])
        if not isinstance(assertions, list) or not assertions:
            raise RuntimeError(f"{row['用例编号']} 断言规则为空")
        if any(char in value for row in rows for value in row.values() for char in ("\r", "\n")):
            raise RuntimeError("CSV 单元格包含换行，无法保持单行记录")

    raw = OUTPUT_PATH.read_text(encoding="utf-8-sig")
    if "192.168.120.82" in raw or "192.168.115.16" in raw:
        raise RuntimeError("CSV 仍包含内部服务地址")
    if not raw.startswith('"用例编号"'):
        raise RuntimeError("CSV 首行异常")


def main() -> int:
    rows = build_rows()
    write_csv(rows)
    validate_csv(rows)
    physical_lines = OUTPUT_PATH.read_text(encoding="utf-8-sig").count("\n")
    print(f"OUTPUT={OUTPUT_PATH}")
    print(f"ROWS={len(rows)}")
    print(f"COLUMNS={len(FIELDS)}")
    print(f"PHYSICAL_LINES={physical_lines}")
    print(f"BYTES={OUTPUT_PATH.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
