"""UI 测试执行记录 API."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.project import Project
from app.models.ui_test_record import UiTestRecord
from app.schemas.common import DataResponse, PageResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _parse_date(date_str: str | None, end_of_day: bool = False) -> datetime | None:
    """解析 YYYY-MM-DD 日期字符串为 datetime.

    end_of_day 为 True 时返回当天 23:59:59，否则返回当天 00:00:00。
    解析失败时返回 None（忽略该筛选条件）。
    """
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    except ValueError:
        return None


def _serialize_record(r: UiTestRecord, project_name: str | None = None) -> dict:
    """序列化执行记录为字典（不含 step_results）。"""
    return {
        "id": r.id,
        "case_id": r.case_id,
        "case_title": r.case_title,
        "project_id": r.project_id,
        "project_name": project_name,
        "url": r.url,
        "browser_type": r.browser_type,
        "status": r.status,
        "total_steps": r.total_steps,
        "passed_steps": r.passed_steps,
        "failed_steps": r.failed_steps,
        "duration": r.duration,
        "error": r.error,
        "triggered_by": r.triggered_by,
        "executed_at": r.executed_at.isoformat() if r.executed_at else None,
    }


def _passed_sum() -> "func.sum":
    """构造 passed 状态计数表达式。"""
    return func.sum(case((UiTestRecord.status == "passed", 1), else_=0))


def _failed_sum() -> "func.sum":
    """构造 failed/error 状态计数表达式。"""
    return func.sum(case((UiTestRecord.status.in_(["failed", "error"]), 1), else_=0))


# ---------------------------------------------------------------------------
# 列表查询（分页，支持 project_id/case_id/status/日期范围 筛选）
# ---------------------------------------------------------------------------

@router.get("", response_model=PageResponse[dict])
def list_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    case_id: str | None = Query(None, description="按用例筛选"),
    status: str | None = Query(None, description="按状态筛选 passed/failed/error"),
    start_date: str | None = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """UI 测试执行记录列表（分页，关联 Project 表获取项目名称）。"""
    # 关联查询 Project 表获取 project_name
    query = (
        select(UiTestRecord, Project.name)
        .outerjoin(Project, UiTestRecord.project_id == Project.id)
    )
    count_query = select(func.count()).select_from(UiTestRecord)

    # 条件筛选
    conditions = []
    if project_id is not None:
        conditions.append(UiTestRecord.project_id == project_id)
    if case_id is not None:
        conditions.append(UiTestRecord.case_id == case_id)
    if status is not None:
        conditions.append(UiTestRecord.status == status)

    start_dt = _parse_date(start_date, end_of_day=False)
    if start_dt is not None:
        conditions.append(UiTestRecord.executed_at >= start_dt)
    end_dt = _parse_date(end_date, end_of_day=True)
    if end_dt is not None:
        conditions.append(UiTestRecord.executed_at <= end_dt)

    for cond in conditions:
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = db.execute(count_query).scalar_one()

    rows = (
        db.execute(
            query.order_by(UiTestRecord.executed_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )

    data = [_serialize_record(record, project_name) for record, project_name in rows]

    return PageResponse(data=data, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# 获取单条记录详情
# ---------------------------------------------------------------------------

@router.get("/{record_id}", response_model=DataResponse[dict])
def get_record(record_id: str, db: Session = Depends(get_db)):
    """获取单条执行记录详情（含 step_results）。"""
    record = db.get(UiTestRecord, record_id)
    if not record:
        raise NotFoundError("UI 测试执行记录", record_id)

    # 查询项目名称
    project_name = None
    if record.project_id:
        project = db.get(Project, record.project_id)
        if project:
            project_name = project.name

    data = _serialize_record(record, project_name)
    data["step_results"] = record.step_results
    return DataResponse(data=data)


# ---------------------------------------------------------------------------
# 按项目统计
# ---------------------------------------------------------------------------

@router.get("/stats/by-project", response_model=DataResponse[list])
def stats_by_project(db: Session = Depends(get_db)):
    """按项目统计 UI 测试执行情况.

    返回每个项目的: project_id, project_name, total_runs, passed, failed,
    avg_duration, last_run_at
    """
    query = (
        select(
            UiTestRecord.project_id,
            Project.name.label("project_name"),
            func.count().label("total_runs"),
            _passed_sum().label("passed"),
            _failed_sum().label("failed"),
            func.avg(UiTestRecord.duration).label("avg_duration"),
            func.max(UiTestRecord.executed_at).label("last_run_at"),
        )
        .outerjoin(Project, UiTestRecord.project_id == Project.id)
        .group_by(UiTestRecord.project_id, Project.name)
        .order_by(func.count().desc())
    )

    rows = db.execute(query).all()

    data = []
    for row in rows:
        data.append({
            "project_id": row.project_id,
            "project_name": row.project_name or "未分类",
            "total_runs": int(row.total_runs or 0),
            "passed": int(row.passed or 0),
            "failed": int(row.failed or 0),
            "avg_duration": round(float(row.avg_duration or 0), 3),
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        })

    return DataResponse(data=data)


# ---------------------------------------------------------------------------
# 按日期统计趋势
# ---------------------------------------------------------------------------

@router.get("/stats/trend", response_model=DataResponse[dict])
def stats_trend(
    days: int = Query(7, ge=1, le=90, description="统计最近 N 天"),
    db: Session = Depends(get_db),
):
    """按日期统计最近 N 天的执行趋势.

    返回每天的 total/passed/failed，无数据的天补 0。
    """
    today = datetime.now().date()
    start_dt = datetime.combine(today - timedelta(days=days - 1), datetime.min.time())

    date_col = func.date(UiTestRecord.executed_at).label("day")
    query = (
        select(
            date_col,
            func.count().label("total"),
            _passed_sum().label("passed"),
            _failed_sum().label("failed"),
        )
        .where(UiTestRecord.executed_at >= start_dt)
        .group_by(date_col)
        .order_by(date_col)
    )

    rows = db.execute(query).all()

    # 构建日期映射
    day_map: dict[str, dict] = {}
    for row in rows:
        day_str = str(row.day)
        day_map[day_str] = {
            "date": day_str,
            "total": int(row.total or 0),
            "passed": int(row.passed or 0),
            "failed": int(row.failed or 0),
        }

    # 填充缺失日期（补 0）
    trend = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        day_str = d.strftime("%Y-%m-%d")
        trend.append(day_map.get(day_str, {
            "date": day_str,
            "total": 0,
            "passed": 0,
            "failed": 0,
        }))

    return DataResponse(data={"trend": trend, "days": days})


# ---------------------------------------------------------------------------
# 日志查询（从 step_results 中提取日志信息）
# ---------------------------------------------------------------------------

@router.get("/logs/search", response_model=PageResponse[dict])
def search_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, description="搜索关键词（匹配用例标题和错误信息）"),
    level: str | None = Query(None, description="日志级别 error/warn/info"),
    project_id: str | None = Query(None, description="按项目筛选"),
    start_date: str | None = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """日志查询：从执行记录中提取日志条目.

    - error 字段作为 error 级别日志
    - status=failed 的记录提取失败步骤作为 warn 日志
    - 其他步骤作为 info 日志
    - 支持 keyword 模糊搜索 case_title 和 error 字段
    """
    # 基础查询：关联 Project 表获取项目名称
    query = (
        select(UiTestRecord, Project.name)
        .outerjoin(Project, UiTestRecord.project_id == Project.id)
    )

    conditions = []
    if project_id is not None:
        conditions.append(UiTestRecord.project_id == project_id)
    if keyword:
        conditions.append(
            UiTestRecord.case_title.like(f"%{keyword}%")
            | UiTestRecord.error.like(f"%{keyword}%")
        )
    start_dt = _parse_date(start_date, end_of_day=False)
    if start_dt is not None:
        conditions.append(UiTestRecord.executed_at >= start_dt)
    end_dt = _parse_date(end_date, end_of_day=True)
    if end_dt is not None:
        conditions.append(UiTestRecord.executed_at <= end_dt)

    for cond in conditions:
        query = query.where(cond)

    # 获取匹配的记录（按时间倒序，限制数量避免内存问题）
    rows = (
        db.execute(
            query.order_by(UiTestRecord.executed_at.desc()).limit(1000)
        )
        .all()
    )

    # 从记录中提取日志条目
    logs: list[dict] = []
    for record, project_name in rows:
        executed_at_str = (
            record.executed_at.isoformat() if record.executed_at else None
        )

        # error 字段 → error 级别日志
        if record.error:
            if level is None or level == "error":
                logs.append({
                    "record_id": record.id,
                    "case_title": record.case_title,
                    "project_id": record.project_id,
                    "project_name": project_name,
                    "level": "error",
                    "message": record.error,
                    "timestamp": executed_at_str,
                    "executed_at": executed_at_str,
                    "step_info": None,
                })

        # 从 step_results 提取步骤日志
        step_results = record.step_results or []
        for step in step_results:
            step_status = step.get("status", "")
            # 失败步骤 → warn 级别，其他 → info 级别
            log_level = "warn" if step_status == "failed" else "info"

            # 级别筛选
            if level is not None and log_level != level:
                continue

            step_info = {
                "step": step.get("step"),
                "action": step.get("action"),
                "description": step.get("description"),
            }
            message = (
                step.get("message")
                or step.get("error")
                or step.get("description")
                or ""
            )

            logs.append({
                "record_id": record.id,
                "case_title": record.case_title,
                "project_id": record.project_id,
                "project_name": project_name,
                "level": log_level,
                "message": message,
                "timestamp": executed_at_str,
                "executed_at": executed_at_str,
                "step_info": step_info,
            })

    # 分页（日志已按记录时间倒序排列）
    total = len(logs)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_logs = logs[start_idx:end_idx]

    return PageResponse(data=page_logs, total=total, page=page, page_size=page_size)
