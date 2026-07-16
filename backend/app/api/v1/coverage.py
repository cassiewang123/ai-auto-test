"""接口覆盖率看板 API.

统计接口定义与测试覆盖情况：
- total_endpoints: 按 method+url 去重的接口数
- covered: 有测试用例覆盖的接口数
- by_method: 按请求方法分布的覆盖率
- by_group: 按分组统计覆盖率
- recent_runs: 最近执行的覆盖率趋势
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TestCase, TestResult
from app.models.test_run_summary import TestRunSummary
from app.schemas.common import DataResponse

router = APIRouter()


@router.get("", response_model=DataResponse[dict])
def get_coverage(
    project_id: str | None = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
):
    """获取接口覆盖率统计."""
    # 基础过滤条件
    case_filter = []
    if project_id is not None:
        case_filter.append(TestCase.project_id == project_id)

    # 1. 按 method+url 去重统计已定义接口数
    endpoint_query = select(
        TestCase.method,
        TestCase.url,
    ).where(*case_filter).group_by(TestCase.method, TestCase.url)
    endpoints = db.execute(endpoint_query).all()

    total_endpoints = len(endpoints)

    # 2. 统计有执行记录覆盖的接口数（method+url 在 TestResult 关联的 TestCase 中出现过）
    # 通过 TestCase 与 TestResult 关联，找出有执行结果的 method+url 组合
    covered_query = (
        select(TestCase.method, TestCase.url)
        .join(TestResult, TestResult.test_case_id == TestCase.id)
        .where(*case_filter)
        .group_by(TestCase.method, TestCase.url)
    )
    covered_endpoints = db.execute(covered_query).all()
    covered_set = {(r.method, r.url) for r in covered_endpoints}
    covered = len(covered_set)

    coverage_rate = round(covered / total_endpoints * 100, 1) if total_endpoints > 0 else 0.0

    # 3. 按方法分布统计
    by_method_map: dict[str, dict] = {}
    for ep in endpoints:
        m = ep.method or "UNKNOWN"
        if m not in by_method_map:
            by_method_map[m] = {"total": 0, "covered": 0}
        by_method_map[m]["total"] += 1
        if (ep.method, ep.url) in covered_set:
            by_method_map[m]["covered"] += 1

    by_method = []
    for m, v in sorted(by_method_map.items()):
        rate = round(v["covered"] / v["total"] * 100, 1) if v["total"] > 0 else 0.0
        by_method.append({
            "method": m,
            "total": v["total"],
            "covered": v["covered"],
            "uncovered": v["total"] - v["covered"],
            "coverage_rate": rate,
        })

    # 4. 按分组统计覆盖率
    group_query = (
        select(
            func.coalesce(TestCase.group_path, "未分组").label("group_path"),
            func.count(func.distinct(func.concat(TestCase.method, TestCase.url))).label("total"),
        )
        .where(*case_filter)
        .group_by(func.coalesce(TestCase.group_path, "未分组"))
    )
    group_rows = db.execute(group_query).all()

    # 各分组覆盖数
    group_covered_query = (
        select(
            func.coalesce(TestCase.group_path, "未分组").label("group_path"),
            func.count(func.distinct(func.concat(TestCase.method, TestCase.url))).label("covered"),
        )
        .join(TestResult, TestResult.test_case_id == TestCase.id)
        .where(*case_filter)
        .group_by(func.coalesce(TestCase.group_path, "未分组"))
    )
    group_covered_rows = db.execute(group_covered_query).all()
    group_covered_map = {r.group_path: r.covered for r in group_covered_rows}

    by_group = []
    for gr in group_rows:
        gcov = group_covered_map.get(gr.group_path, 0)
        rate = round(gcov / gr.total * 100, 1) if gr.total > 0 else 0.0
        by_group.append({
            "group_path": gr.group_path,
            "total": gr.total,
            "covered": gcov,
            "uncovered": gr.total - gcov,
            "coverage_rate": rate,
        })
    by_group.sort(key=lambda x: x["total"], reverse=True)

    # 5. 最近执行的覆盖率趋势（基于 TestRunSummary）
    recent_runs_query = (
        select(TestRunSummary)
        .order_by(desc(TestRunSummary.created_at))
        .limit(10)
    )
    if project_id is not None:
        recent_runs_query = recent_runs_query.where(TestRunSummary.project_id == project_id)
    recent_runs = db.execute(recent_runs_query).scalars().all()
    recent_runs = list(reversed(recent_runs))  # 时间正序

    recent_runs_data = [{
        "run_id": r.run_id,
        "total": r.total,
        "passed": r.passed,
        "failed": r.failed,
        "error": r.error,
        "pass_rate": round(r.passed / r.total * 100, 1) if r.total > 0 else 0,
        "created_at": r.created_at.strftime("%m-%d %H:%M") if r.created_at else "",
    } for r in recent_runs]

    return DataResponse(data={
        "total_endpoints": total_endpoints,
        "covered": covered,
        "uncovered": total_endpoints - covered,
        "coverage_rate": coverage_rate,
        "by_method": by_method,
        "by_group": by_group,
        "recent_runs": recent_runs_data,
    })
