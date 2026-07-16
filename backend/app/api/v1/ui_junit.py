"""UI 测试 JUnit XML 报告输出.

提供两个端点：
- GET /ui-test-records/{record_id}/junit：单条执行记录的 JUnit XML
- GET /ui-test-suites/runs/{run_id}/junit：套件执行的 JUnit XML

JUnit XML 格式遵循标准：
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="..." tests="10" failures="2" errors="1" time="123.4">
  <testcase name="case1" classname="SuiteName" time="1.2"/>
  <testcase name="case2" classname="SuiteName" time="2.3">
    <failure message="...">stack trace</failure>
  </testcase>
</testsuite>
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.ui_test_record import UiTestRecord
from app.models.ui_test_suite import UiTestSuiteRun

router = APIRouter()


# ---------------------------------------------------------------------------
# JUnit XML 生成辅助函数
# ---------------------------------------------------------------------------

def _build_testcase_element(
    name: str,
    classname: str,
    time_sec: float,
    status: str,
    error: str | None,
) -> ET.Element:
    """构建单个 testcase 元素，根据 status 添加 failure / error 子节点."""
    tc = ET.Element(
        "testcase",
        {
            "name": name,
            "classname": classname,
            "time": f"{time_sec:.3f}",
        },
    )
    # status=passed：无子节点
    # status=failed：failure
    # status=error：error
    if status == "failed":
        failure = ET.SubElement(
            tc, "failure", {"message": (error or "测试失败")[:500]}
        )
        failure.text = error or "测试失败"
    elif status == "error":
        err_el = ET.SubElement(
            tc, "error", {"message": (error or "执行错误")[:500]}
        )
        err_el.text = error or "执行错误"
    elif status != "passed":
        # 其他未知状态按 error 处理
        err_el = ET.SubElement(
            tc, "error", {"message": f"未知状态: {status}"}
        )
        err_el.text = error or f"未知状态: {status}"
    return tc


def _build_suite_xml(
    suite_name: str,
    records: list[dict],
    total_time: float,
) -> str:
    """根据执行记录列表生成 JUnit testsuite XML 字符串.

    records 中每项需含: name, status, time, error
    """
    tests = len(records)
    failures = sum(1 for r in records if r.get("status") == "failed")
    errors = sum(1 for r in records if r.get("status") == "error")

    suite = ET.Element(
        "testsuite",
        {
            "name": suite_name,
            "tests": str(tests),
            "failures": str(failures),
            "errors": str(errors),
            "time": f"{total_time:.3f}",
            "timestamp": datetime.now().isoformat(),
        },
    )

    for r in records:
        tc = _build_testcase_element(
            name=r.get("name", "unknown"),
            classname=suite_name,
            time_sec=float(r.get("time", 0) or 0),
            status=r.get("status", "error"),
            error=r.get("error"),
        )
        suite.append(tc)

    # 缩进美化（Python 3.9+ 支持 indent）
    try:
        ET.indent(suite, space="  ")
    except AttributeError:
        pass

    xml_str = ET.tostring(suite, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


# ---------------------------------------------------------------------------
# 端点：单条执行记录的 JUnit XML
# ---------------------------------------------------------------------------

@router.get("/ui-test-records/{record_id}/junit")
def get_record_junit(record_id: str, db: Session = Depends(get_db)):
    """返回单条 UI 测试执行记录的 JUnit XML 报告."""
    record = db.get(UiTestRecord, record_id)
    if not record:
        raise NotFoundError("UI 测试执行记录", record_id)

    xml_content = _build_suite_xml(
        suite_name=record.case_title or "UI Test",
        records=[
            {
                "name": record.case_title or record.id,
                "status": record.status,
                "time": record.duration or 0,
                "error": record.error,
            }
        ],
        total_time=record.duration or 0,
    )
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ui-record-{record_id}.xml"'
            )
        },
    )


# ---------------------------------------------------------------------------
# 端点：套件执行的 JUnit XML
# ---------------------------------------------------------------------------

@router.get("/ui-test-suites/runs/{run_id}/junit")
def get_suite_run_junit(run_id: str, db: Session = Depends(get_db)):
    """返回套件执行的 JUnit XML 报告（包含套件内所有用例执行结果）."""
    run = db.get(UiTestSuiteRun, run_id)
    if not run:
        raise NotFoundError("套件执行记录", run_id)

    # 查询关联的所有用例执行记录
    records: list[dict] = []
    if run.record_ids:
        from sqlalchemy import select
        rows = (
            db.execute(
                select(UiTestRecord).where(UiTestRecord.id.in_(run.record_ids))
            )
            .scalars()
            .all()
        )
        record_map = {r.id: r for r in rows}
        for rid in run.record_ids:
            r = record_map.get(rid)
            if r:
                records.append({
                    "name": r.case_title or r.id,
                    "status": r.status,
                    "time": r.duration or 0,
                    "error": r.error,
                })

    xml_content = _build_suite_xml(
        suite_name=run.suite_name or "UI Test Suite",
        records=records,
        total_time=run.duration or 0,
    )
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ui-suite-run-{run_id}.xml"'
            )
        },
    )
