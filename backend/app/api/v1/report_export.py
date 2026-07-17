"""报告导出 API：支持导出 HTML 与 PDF 格式的测试报告.

使用 Python 字符串模板渲染 HTML（无需额外依赖）；
PDF 导出尝试使用 reportlab，若不可用则降级返回 HTML 并提示用户使用浏览器打印。
"""
from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models import TestCase, TestResult
from app.models.execution_job import ExecutionJob
from app.models.test_run_summary import TestRunSummary
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.execution.job_reporting import normalize_job_run
from app.services.project_access import ensure_resource_role

router = APIRouter()

_REPORTABLE_JOB_STATUSES = {"succeeded", "failed", "cancelled", "timed_out"}


def _status_sum(status: str):
    """构造某状态的计数表达式."""
    return func.sum(case((TestResult.status == status, 1), else_=0))


def _job_export_data(db: Session, job: ExecutionJob) -> dict:
    run = normalize_job_run(db, job, include_results=True)
    return {
        "run_id": run["run_id"],
        "total": run.get("total", 0),
        "passed": run.get("passed", 0),
        "failed": run.get("failed", 0),
        "error": run.get("error", 0),
        "skipped": run.get("skipped", 0),
        "duration": round(float(run.get("duration") or 0.0), 3),
        "pass_rate": run.get("pass_rate", 0.0),
        "created_at": run.get("created_at"),
        "source": run.get("source") or "job",
        "results": [
            {
                "title": str(result.get("title") or "(已删除)"),
                "method": str(result.get("method") or ""),
                "url": str(result.get("url") or ""),
                "status": str(result.get("status") or "unknown"),
                "duration": round(float(result.get("duration") or 0.0), 4),
                "status_code": result.get("status_code"),
                "error": result.get("error") or result.get("error_message"),
            }
            for result in run.get("results", [])
            if isinstance(result, dict)
        ],
    }


def _gather_run_data(run_id: str, db: Session, user: User) -> dict:
    """汇总某次执行的数据，供渲染报告使用."""
    job = db.get(ExecutionJob, run_id)
    if job is not None and job.status in _REPORTABLE_JOB_STATUSES:
        ensure_resource_role(db, user, job, "viewer")
        return _job_export_data(db, job)

    summary = db.execute(
        select(TestRunSummary).where(TestRunSummary.run_id == run_id)
    ).scalars().first()

    # 优先使用 TestRunSummary，没有则从 TestResult 聚合
    if summary:
        ensure_resource_role(db, user, summary, "viewer")
        total = summary.total
        passed = summary.passed
        failed = summary.failed
        error = summary.error
        skipped = summary.skipped
        duration = round(summary.duration, 3)
        created_at = summary.created_at
        source = summary.source
    else:
        if not user.is_superuser:
            raise NotFoundError("执行记录", run_id)
        row = db.execute(
            select(
                func.count().label("total"),
                _status_sum("passed").label("passed"),
                _status_sum("failed").label("failed"),
                _status_sum("error").label("error"),
                _status_sum("skipped").label("skipped"),
                func.coalesce(func.sum(TestResult.duration), 0.0).label("duration_sum"),
            ).where(TestResult.run_id == run_id)
        ).one()
        total = row.total or 0
        passed = int(row.passed or 0)
        failed = int(row.failed or 0)
        error = int(row.error or 0)
        skipped = int(row.skipped or 0)
        duration = round(float(row.duration_sum or 0.0), 3)
        first = db.execute(
            select(TestResult.executed_at)
            .where(TestResult.run_id == run_id)
            .order_by(TestResult.executed_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        created_at = first
        source = "manual"

    pass_rate = round(passed / total * 100, 1) if total > 0 else 0.0

    # 明细结果
    results = db.execute(
        select(TestResult).where(TestResult.run_id == run_id)
    ).scalars().all()
    detail = []
    for r in results:
        case_obj = db.get(TestCase, r.test_case_id)
        detail.append({
            "title": case_obj.title if case_obj else "(已删除)",
            "method": case_obj.method if case_obj else "",
            "url": case_obj.url if case_obj else "",
            "status": r.status,
            "duration": round(r.duration, 4),
            "status_code": (r.response_snapshot or {}).get("status_code") if r.response_snapshot else None,
            "error": r.error_message,
        })

    return {
        "run_id": run_id,
        "total": total,
        "passed": passed,
        "failed": failed,
        "error": error,
        "skipped": skipped,
        "duration": duration,
        "pass_rate": pass_rate,
        "created_at": created_at,
        "source": source,
        "results": detail,
    }


def _render_html_report(data: dict) -> str:
    """用 Python 字符串模板渲染 HTML 报告."""
    created_str = ""
    if data["created_at"]:
        if isinstance(data["created_at"], datetime):
            created_str = data["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_str = str(data["created_at"])

    pass_rate = data["pass_rate"]
    rate_color = "#16a34a" if pass_rate >= 80 else "#d97706" if pass_rate >= 50 else "#dc2626"

    # 用例结果行
    rows_html = []
    status_label = {"passed": "通过", "failed": "失败", "error": "错误", "skipped": "跳过"}
    status_color = {"passed": "#16a34a", "failed": "#dc2626", "error": "#d97706", "skipped": "#6b7280"}
    method_color = {"GET": "#16a34a", "POST": "#ea580c", "PUT": "#2563eb", "PATCH": "#7c3aed", "DELETE": "#dc2626"}

    for idx, r in enumerate(data["results"], 1):
        st = r["status"] or "unknown"
        st_label = status_label.get(st, st)
        st_color = status_color.get(st, "#6b7280")
        m = r["method"] or ""
        m_color = method_color.get(m, "#6b7280")
        err = html.escape(r["error"] or "") if r["error"] else "-"
        rows_html.append(f"""
        <tr>
          <td>{idx}</td>
          <td><span class="method-tag" style="background:{m_color}">{html.escape(m)}</span></td>
          <td class="cell-title">{html.escape(r["title"])}</td>
          <td class="cell-url">{html.escape(r["url"])}</td>
          <td><span class="status-tag" style="background:{st_color}">{st_label}</span></td>
          <td>{r["status_code"] or "-"}</td>
          <td>{r["duration"]:.3f}s</td>
          <td class="cell-error">{err}</td>
        </tr>""")

    if not rows_html:
        rows_html.append('<tr><td colspan="8" style="text-align:center;padding:24px;color:#9ca3af">暂无用例结果</td></tr>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>测试报告 - {html.escape(data["run_id"][:8])}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f9fafb; color: #1f2937; padding: 24px; }}
  .report-header {{ background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #fff; padding: 32px; border-radius: 12px; margin-bottom: 24px; }}
  .report-header h1 {{ font-size: 24px; margin-bottom: 8px; }}
  .report-header .meta {{ font-size: 13px; opacity: 0.9; }}
  .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .summary-card {{ background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; }}
  .summary-card .value {{ font-size: 32px; font-weight: 700; margin-bottom: 4px; }}
  .summary-card .label {{ font-size: 13px; color: #6b7280; }}
  .pass-rate {{ color: {rate_color}; }}
  .pass-color {{ color: #16a34a; }}
  .fail-color {{ color: #dc2626; }}
  .error-color {{ color: #d97706; }}
  .skip-color {{ color: #6b7280; }}
  .progress-bar {{ background: #e5e7eb; border-radius: 999px; height: 12px; overflow: hidden; margin: 12px 0; }}
  .progress-fill {{ background: {rate_color}; height: 100%; width: {pass_rate}%; border-radius: 999px; transition: width 0.3s; }}
  .section-title {{ font-size: 18px; font-weight: 600; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 2px solid #4f46e5; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  th {{ background: #f3f4f6; padding: 12px; text-align: left; font-size: 13px; color: #6b7280; font-weight: 600; }}
  td {{ padding: 10px 12px; border-top: 1px solid #f3f4f6; font-size: 13px; }}
  tr:hover td {{ background: #f9fafb; }}
  .method-tag, .status-tag {{ color: #fff; padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; display: inline-block; min-width: 44px; text-align: center; }}
  .cell-title {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .cell-url {{ max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #6b7280; font-family: monospace; font-size: 12px; }}
  .cell-error {{ max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #dc2626; font-size: 12px; }}
  .footer {{ margin-top: 32px; text-align: center; color: #9ca3af; font-size: 12px; }}
  @media print {{ body {{ padding: 0; background: #fff; }} .report-header {{ border-radius: 0; }} }}
</style>
</head>
<body>
  <div class="report-header">
    <h1>自动化测试报告</h1>
    <div class="meta">
      执行批次: {html.escape(data["run_id"])} &nbsp;|&nbsp;
      执行时间: {created_str} &nbsp;|&nbsp;
      来源: {html.escape(data["source"])}
    </div>
  </div>

  <div class="summary-cards">
    <div class="summary-card">
      <div class="value">{data["total"]}</div>
      <div class="label">用例总数</div>
    </div>
    <div class="summary-card">
      <div class="value pass-color">{data["passed"]}</div>
      <div class="label">通过</div>
    </div>
    <div class="summary-card">
      <div class="value fail-color">{data["failed"]}</div>
      <div class="label">失败</div>
    </div>
    <div class="summary-card">
      <div class="value error-color">{data["error"]}</div>
      <div class="label">错误</div>
    </div>
    <div class="summary-card">
      <div class="value skip-color">{data["skipped"]}</div>
      <div class="label">跳过</div>
    </div>
    <div class="summary-card">
      <div class="value">{data["duration"]}s</div>
      <div class="label">总耗时</div>
    </div>
    <div class="summary-card">
      <div class="value pass-rate">{pass_rate}%</div>
      <div class="label">通过率</div>
    </div>
  </div>

  <div class="progress-bar"><div class="progress-fill"></div></div>

  <div class="section-title">用例结果明细</div>
  <table>
    <thead>
      <tr>
        <th style="width:50px">#</th>
        <th style="width:70px">方法</th>
        <th>用例标题</th>
        <th>请求 URL</th>
        <th style="width:80px">状态</th>
        <th style="width:80px">状态码</th>
        <th style="width:90px">耗时</th>
        <th>错误信息</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>

  <div class="footer">
    报告生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | AI 测试平台
  </div>
</body>
</html>"""


@router.get("/{run_id}/html")
def export_html(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出 HTML 格式的测试报告."""
    data = _gather_run_data(run_id, db, current_user)
    html_content = _render_html_report(data)
    filename = quote(f"测试报告_{run_id[:8]}.html")
    return Response(
        content=html_content.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )


@router.get("/{run_id}/pdf")
def export_pdf(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出 PDF 格式的测试报告.

    尝试使用 reportlab 生成 PDF；若 reportlab 不可用，则降级返回 HTML
    并通过响应头提示用户使用浏览器打印为 PDF。
    """
    data = _gather_run_data(run_id, db, current_user)

    try:
        import io

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        # 尝试注册中文字体
        font_name = "Helvetica"
        for font_path in [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]:
            try:
                pdfmetrics.registerFont(TTFont("CNFont", font_path))
                font_name = "CNFont"
                break
            except Exception:
                continue

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("Title", parent=styles["Title"], fontName=font_name, fontSize=20, textColor=colors.HexColor("#4f46e5"))
        meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontName=font_name, fontSize=9, textColor=colors.grey)
        section_style = ParagraphStyle("Section", parent=styles["Heading2"], fontName=font_name, fontSize=14, textColor=colors.HexColor("#4f46e5"))

        elements = []
        elements.append(Paragraph("自动化测试报告", title_style))
        elements.append(Spacer(1, 6 * mm))

        created_str = ""
        if data["created_at"]:
            if isinstance(data["created_at"], datetime):
                created_str = data["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            else:
                created_str = str(data["created_at"])
        elements.append(Paragraph(
            f"执行批次: {data['run_id']} | 执行时间: {created_str} | 来源: {data['source']}",
            meta_style,
        ))
        elements.append(Spacer(1, 8 * mm))

        # 汇总统计表
        elements.append(Paragraph("执行概览", section_style))
        elements.append(Spacer(1, 4 * mm))
        summary_data = [
            ["指标", "值"],
            ["用例总数", str(data["total"])],
            ["通过", str(data["passed"])],
            ["失败", str(data["failed"])],
            ["错误", str(data["error"])],
            ["跳过", str(data["skipped"])],
            ["总耗时", f"{data['duration']}s"],
            ["通过率", f"{data['pass_rate']}%"],
        ]
        summary_table = Table(summary_data, colWidths=[60 * mm, 40 * mm])
        summary_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BOX", (0, 0), (-1, -1), 1, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 10 * mm))

        # 用例明细表
        elements.append(Paragraph("用例结果明细", section_style))
        elements.append(Spacer(1, 4 * mm))
        status_label = {"passed": "通过", "failed": "失败", "error": "错误", "skipped": "跳过"}
        detail_rows = [["#", "方法", "标题", "状态", "状态码", "耗时", "错误"]]
        for idx, r in enumerate(data["results"], 1):
            st = status_label.get(r["status"], r["status"])
            err = (r["error"] or "")[:50]
            detail_rows.append([
                str(idx),
                r["method"] or "",
                (r["title"] or "")[:30],
                st,
                str(r["status_code"] or "-"),
                f"{r['duration']:.3f}s",
                err,
            ])
        detail_table = Table(detail_rows, colWidths=[10 * mm, 16 * mm, 45 * mm, 18 * mm, 18 * mm, 20 * mm, 53 * mm])
        detail_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6b7280")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#e5e7eb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(detail_table)

        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        filename = quote(f"测试报告_{run_id[:8]}.pdf")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )
    except ImportError:
        # reportlab 不可用，降级返回 HTML 并提示
        html_content = _render_html_report(data)
        html_with_notice = html_content.replace(
            "<body>",
            "<body><div style='background:#fef3c7;color:#92400e;padding:12px 24px;border-radius:0 0 8px 8px;margin-bottom:16px'>⚠️ PDF 导出依赖 reportlab 库，当前未安装。已返回 HTML 报告，您可使用浏览器打印功能（Ctrl+P）另存为 PDF。</div>",
            1,
        )
        filename = quote(f"测试报告_{run_id[:8]}.html")
        return Response(
            content=html_with_notice.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                "X-Export-Notice": "reportlab-not-installed-fallback-to-html",
            },
        )
