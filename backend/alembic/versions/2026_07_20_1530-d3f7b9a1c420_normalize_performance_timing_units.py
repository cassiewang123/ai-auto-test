"""normalize performance timing units

Revision ID: d3f7b9a1c420
Revises: a7d9e2c4f610
Create Date: 2026-07-20 15:30:00

"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "d3f7b9a1c420"
down_revision: str | None = "a7d9e2c4f610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESULT_TIMING_FIELDS = (
    "avg_response_time",
    "min_response_time",
    "max_response_time",
    "p50",
    "p90",
    "p95",
    "p99",
)
_DETAIL_TIMING_FIELDS = (
    "avg_response_time",
    "min_response_time",
    "max_response_time",
)


def _load_json(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return json.loads(json.dumps(value))
    if hasattr(value, "read"):
        value = value.read()
    if not isinstance(value, str) or not value:
        return None
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else None


def _scale_number(value: Any, factor: float) -> float | None:
    if value is None:
        return None
    return round(float(value) * factor, 4)


def _scale_detail(value: Any, factor: float) -> str | None:
    detail = _load_json(value)
    if detail is None:
        return None
    for stats in detail.values():
        if not isinstance(stats, dict):
            continue
        for field in _DETAIL_TIMING_FIELDS:
            if stats.get(field) is not None:
                stats[field] = _scale_number(stats[field], factor)
    return json.dumps(detail, ensure_ascii=False)


def _scale_sla_details(value: Any, factor: float) -> str | None:
    details = _load_json(value)
    if details is None:
        return None
    response_time = details.get("response_time_p95")
    if isinstance(response_time, dict) and response_time.get("actual") is not None:
        response_time["actual"] = _scale_number(response_time["actual"], factor)
    return json.dumps(details, ensure_ascii=False)


def _transform(factor: float) -> None:
    performance_results = sa.table(
        "performance_results",
        sa.column("id", sa.String(length=36)),
        *[sa.column(field, sa.Float()) for field in _RESULT_TIMING_FIELDS],
        sa.column("detail", sa.Text()),
        sa.column("sla_details", sa.Text()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(performance_results)).mappings().all()

    for row in rows:
        values = {
            field: _scale_number(row[field], factor)
            for field in _RESULT_TIMING_FIELDS
            if row[field] is not None
        }
        scaled_detail = _scale_detail(row["detail"], factor)
        if scaled_detail is not None:
            values["detail"] = scaled_detail
        scaled_sla_details = _scale_sla_details(row["sla_details"], factor)
        if scaled_sla_details is not None:
            values["sla_details"] = scaled_sla_details
        if values:
            connection.execute(
                performance_results.update()
                .where(performance_results.c.id == row["id"])
                .values(**values)
            )


def upgrade() -> None:
    _transform(1000.0)


def downgrade() -> None:
    _transform(0.001)
