"""Performance response-time unit contracts."""

from __future__ import annotations

import pytest

from app.services.perf_runner import _evaluate_sla, _seconds_to_milliseconds


def test_execution_duration_is_converted_to_milliseconds() -> None:
    assert _seconds_to_milliseconds(0.4312) == pytest.approx(431.2)
    assert _seconds_to_milliseconds(-1) == 0


def test_sla_response_time_uses_milliseconds() -> None:
    status, details = _evaluate_sla(
        {"response_time_p95": 500},
        p95=431.2,
        error_rate_pct=0,
        rps=1,
    )

    assert status == "passed"
    assert details["response_time_p95"] == {
        "threshold": 500.0,
        "actual": 431.2,
        "status": "pass",
    }

    failed_status, failed_details = _evaluate_sla(
        {"response_time_p95": 500},
        p95=550,
        error_rate_pct=0,
        rps=1,
    )

    assert failed_status == "failed"
    assert failed_details["response_time_p95"]["status"] == "fail"
