"""报告查询 API 测试（TDD：先写测试）。

报告数据没有写入 API，因此通过 db_session 直接播种 TestResult 记录，
再以 client 发起请求验证查询逻辑（client 与 db_session 共享同一内存库）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import app.models  # noqa: F401  注册模型元数据
import pytest

BASE = "/api/v1/reports"


def _seed(
    db_session,
    *,
    run_id="run-1",
    status="passed",
    duration=1.0,
    executed_at=None,
    test_case_id="tc-1",
    **extra,
):
    from app.models import TestResult

    result = TestResult(
        run_id=run_id,
        test_case_id=test_case_id,
        status=status,
        duration=duration,
        executed_at=executed_at or datetime(2026, 7, 1, 10, 0, 0),
        **extra,
    )
    db_session.add(result)
    db_session.commit()
    return result


# ---------------------------------------------------------------------------
# 按 run_id 查询结果列表
# ---------------------------------------------------------------------------
class TestRunResults:
    def test_list_results_by_run_id(self, client, db_session):
        _seed(db_session, run_id="run-1")
        _seed(db_session, run_id="run-1")
        _seed(db_session, run_id="run-2")  # 其它 run 不应出现
        resp = client.get(f"{BASE}/runs/run-1/results")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["total"] == 2
        assert len(body["data"]) == 2
        for item in body["data"]:
            assert item["run_id"] == "run-1"

    def test_list_results_pagination(self, client, db_session):
        for _ in range(3):
            _seed(db_session, run_id="run-1")
        resp = client.get(f"{BASE}/runs/run-1/results?page=1&page_size=2")
        body = resp.json()
        assert body["total"] == 3
        assert len(body["data"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

        resp2 = client.get(f"{BASE}/runs/run-1/results?page=2&page_size=2")
        assert len(resp2.json()["data"]) == 1

    def test_list_results_empty_run(self, client):
        resp = client.get(f"{BASE}/runs/nonexistent/results")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["data"] == []

    def test_results_contain_fields(self, client, db_session):
        _seed(
            db_session,
            run_id="run-x",
            status="failed",
            duration=2.5,
            request_snapshot={"method": "GET", "url": "/api/x"},
            response_snapshot={"status_code": 500},
            assertion_results=[{"assertion_type": "status_code", "passed": False}],
            error_message="服务器内部错误",
        )
        resp = client.get(f"{BASE}/runs/run-x/results")
        item = resp.json()["data"][0]
        assert item["status"] == "failed"
        assert item["duration"] == 2.5
        assert item["request_snapshot"]["url"] == "/api/x"
        assert item["response_snapshot"]["status_code"] == 500
        assert len(item["assertion_results"]) == 1
        assert item["error_message"] == "服务器内部错误"
        assert item["executed_at"]


# ---------------------------------------------------------------------------
# 汇总统计
# ---------------------------------------------------------------------------
class TestRunSummary:
    def test_summary(self, client, db_session):
        _seed(db_session, run_id="run-1", status="passed", duration=1.5)
        _seed(db_session, run_id="run-1", status="passed", duration=2.0)
        _seed(db_session, run_id="run-1", status="failed", duration=0.5)
        _seed(db_session, run_id="run-1", status="skipped", duration=0.0)
        _seed(db_session, run_id="run-2", status="passed", duration=9.0)  # 不计入

        resp = client.get(f"{BASE}/runs/run-1/summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["run_id"] == "run-1"
        assert data["total"] == 4
        assert data["passed"] == 2
        assert data["failed"] == 1
        assert data["skipped"] == 1
        assert data["duration_sum"] == pytest.approx(4.0)

    def test_summary_empty(self, client):
        resp = client.get(f"{BASE}/runs/nonexistent/summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["passed"] == 0
        assert data["failed"] == 0
        assert data["skipped"] == 0
        assert data["duration_sum"] == 0.0


# ---------------------------------------------------------------------------
# 历史趋势
# ---------------------------------------------------------------------------
class TestTrends:
    def test_trends_grouped_by_day(self, client, db_session):
        day1 = datetime(2026, 7, 1, 10, 0, 0)
        day2 = datetime(2026, 7, 2, 15, 0, 0)
        _seed(db_session, executed_at=day1, status="passed")
        _seed(db_session, executed_at=day1, status="failed")
        _seed(db_session, executed_at=day2, status="passed")
        # 范围外的数据不应出现
        _seed(db_session, executed_at=datetime(2026, 7, 10, 0, 0, 0), status="passed")

        start = datetime(2026, 6, 30).isoformat()
        end = datetime(2026, 7, 3).isoformat()
        resp = client.get(f"{BASE}/trends?start={start}&end={end}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        # 按日期升序
        assert data[0]["date"] == "2026-07-01"
        assert data[0]["total"] == 2
        assert data[0]["passed"] == 1
        assert data[0]["failed"] == 1
        assert data[1]["date"] == "2026-07-02"
        assert data[1]["total"] == 1
        assert data[1]["passed"] == 1

    def test_trends_empty(self, client):
        start = datetime(2026, 6, 1).isoformat()
        end = datetime(2026, 6, 2).isoformat()
        resp = client.get(f"{BASE}/trends?start={start}&end={end}")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_trends_missing_params_returns_422(self, client):
        # start/end 为必填
        resp = client.get(f"{BASE}/trends")
        assert resp.status_code == 422
