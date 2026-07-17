"""Focused coverage for ExecutionJob-backed reports and legacy compatibility."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import TestCase as ORMTestCase
from app.models import TestResult as ORMTestResult
from app.models.execution_job import ExecutionJob
from app.models.test_run_summary import TestRunSummary as ORMTestRunSummary

BASE = "/api/v1/reports"


def _job(
    *,
    job_id: str,
    created_at: datetime,
    status: str = "succeeded",
    total: int = 1,
    passed: int = 1,
    failed: int = 0,
    error: int = 0,
    skipped: int = 0,
    duration: float = 0.25,
    case_id: str = "unified-case",
) -> ExecutionJob:
    return ExecutionJob(
        id=job_id,
        job_type="api_case",
        resource_id=case_id,
        status=status,
        created_by="test-admin-id",
        created_at=created_at,
        started_at=created_at,
        finished_at=created_at + timedelta(seconds=duration),
        result_summary=f"{job_id} summary",
        config={
            "_result_metrics": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "error": error,
                "skipped": skipped,
                "duration": duration,
                "status_code": 200 if status == "succeeded" else 500,
                "results": [
                    {
                        "case_id": case_id,
                        "title": "Unified API case",
                        "method": "GET",
                        "url": "https://example.test/unified",
                        "status": "passed" if status == "succeeded" else "failed",
                        "duration": duration,
                        "status_code": 200 if status == "succeeded" else 500,
                        "error": None if status == "succeeded" else "request failed",
                    }
                ],
            }
        },
    )


def _legacy_summary(
    *,
    run_id: str,
    created_at: datetime,
    total: int = 2,
    passed: int = 1,
    failed: int = 1,
) -> ORMTestRunSummary:
    return ORMTestRunSummary(
        run_id=run_id,
        source="manual",
        created_by="test-admin-id",
        total=total,
        passed=passed,
        failed=failed,
        duration=1.5,
        created_at=created_at,
    )


def _seed_case(db_session) -> ORMTestCase:
    case = ORMTestCase(
        id="unified-case",
        title="Unified API case",
        method="GET",
        url="https://example.test/unified",
    )
    db_session.add(case)
    db_session.flush()
    return case


def test_runs_merge_jobs_and_legacy_with_job_precedence_and_sorting(
    client,
    db_session,
):
    now = datetime(2026, 7, 17, 10, 0, 0)
    _seed_case(db_session)
    db_session.add_all(
        [
            _legacy_summary(run_id="legacy-only", created_at=now),
            _legacy_summary(
                run_id="duplicate-run",
                created_at=now + timedelta(minutes=5),
                total=99,
                passed=0,
                failed=99,
            ),
            _job(
                job_id="duplicate-run",
                created_at=now + timedelta(minutes=10),
                total=3,
                passed=3,
            ),
            _job(
                job_id="job-only",
                created_at=now + timedelta(minutes=20),
                status="failed",
                passed=0,
                failed=1,
            ),
            _job(
                job_id="running-job",
                created_at=now + timedelta(minutes=30),
                status="running",
                passed=0,
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"{BASE}/runs", params={"limit": 10})

    assert response.status_code == 200
    runs = response.json()["data"]
    assert [run["run_id"] for run in runs] == [
        "job-only",
        "duplicate-run",
        "legacy-only",
    ]
    duplicate = next(run for run in runs if run["run_id"] == "duplicate-run")
    assert duplicate["source"] == "api_case"
    assert duplicate["total"] == 3
    assert duplicate["passed"] == 3


def test_execution_job_detail_returns_summary_and_results(client, db_session):
    created_at = datetime(2026, 7, 17, 11, 0, 0)
    _seed_case(db_session)
    db_session.add(
        _job(
            job_id="job-detail",
            created_at=created_at,
            status="failed",
            passed=0,
            failed=1,
            duration=0.75,
        )
    )
    db_session.commit()

    response = client.get(f"{BASE}/runs/job-detail")

    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["run_id"] == "job-detail"
    assert detail["summary"]["total"] == 1
    assert detail["summary"]["failed"] == 1
    assert detail["summary"]["result_summary"] == "job-detail summary"
    assert detail["results"] == [
        {
            "case_id": "unified-case",
            "title": "Unified API case",
            "method": "GET",
            "url": "https://example.test/unified",
            "status": "failed",
            "duration": 0.75,
            "status_code": 500,
            "error": "request failed",
        }
    ]


def test_trend_uses_deduplicated_runs_in_chronological_order(client, db_session):
    now = datetime(2026, 7, 17, 12, 0, 0)
    _seed_case(db_session)
    db_session.add_all(
        [
            _legacy_summary(run_id="legacy-trend", created_at=now),
            _legacy_summary(
                run_id="trend-duplicate",
                created_at=now + timedelta(minutes=1),
                total=10,
                passed=0,
                failed=10,
            ),
            _job(
                job_id="trend-duplicate",
                created_at=now + timedelta(minutes=2),
                total=4,
                passed=3,
                failed=1,
            ),
            _job(
                job_id="job-trend",
                created_at=now + timedelta(minutes=3),
                total=2,
                passed=2,
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"{BASE}/trend", params={"limit": 3})

    assert response.status_code == 200
    trend = response.json()["data"]
    assert trend["labels"] == ["07-17 12:00", "07-17 12:02", "07-17 12:03"]
    assert trend["totals"] == [2, 4, 2]
    assert trend["passed"] == [1, 3, 2]
    assert trend["failed"] == [1, 1, 0]
    assert trend["pass_rates"] == [50.0, 75.0, 100.0]


def test_report_export_supports_execution_job_and_legacy_run(client, db_session):
    created_at = datetime(2026, 7, 17, 13, 0, 0)
    case = _seed_case(db_session)
    db_session.add_all(
        [
            _job(job_id="job-export", created_at=created_at),
            _legacy_summary(
                run_id="legacy-export",
                created_at=created_at - timedelta(minutes=5),
                total=1,
                passed=1,
                failed=0,
            ),
            ORMTestResult(
                run_id="legacy-export",
                test_case_id=case.id,
                status="passed",
                duration=0.4,
                response_snapshot={"status_code": 204},
                executed_at=created_at - timedelta(minutes=5),
            ),
        ]
    )
    db_session.commit()

    job_response = client.get("/api/v1/report-export/job-export/html")
    legacy_response = client.get("/api/v1/report-export/legacy-export/html")

    assert job_response.status_code == 200
    assert "job-export" in job_response.text
    assert "Unified API case" in job_response.text
    assert legacy_response.status_code == 200
    assert "legacy-export" in legacy_response.text
    assert "Unified API case" in legacy_response.text


def test_legacy_detail_results_summary_and_trends_remain_compatible(
    client,
    db_session,
):
    created_at = datetime(2026, 7, 16, 9, 0, 0)
    case = _seed_case(db_session)
    db_session.add_all(
        [
            _legacy_summary(
                run_id="legacy-compatible",
                created_at=created_at,
                total=1,
                passed=1,
                failed=0,
            ),
            ORMTestResult(
                run_id="legacy-compatible",
                test_case_id=case.id,
                status="passed",
                duration=0.6,
                response_snapshot={"status_code": 200},
                executed_at=created_at,
            ),
        ]
    )
    db_session.commit()

    detail = client.get(f"{BASE}/runs/legacy-compatible")
    results = client.get(f"{BASE}/runs/legacy-compatible/results")
    summary = client.get(f"{BASE}/runs/legacy-compatible/summary")
    trends = client.get(
        f"{BASE}/trends",
        params={
            "start": "2026-07-16T00:00:00",
            "end": "2026-07-17T00:00:00",
        },
    )

    assert detail.status_code == 200
    assert detail.json()["data"]["summary"]["source"] == "manual"
    assert detail.json()["data"]["results"][0]["status_code"] == 200
    assert results.status_code == 200
    assert results.json()["total"] == 1
    assert summary.status_code == 200
    assert summary.json()["data"]["passed"] == 1
    assert trends.status_code == 200
    assert trends.json()["data"][0] == {
        "date": "2026-07-16",
        "total": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
    }
