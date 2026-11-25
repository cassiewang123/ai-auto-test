"""Quality gate parsing, evaluation, and job automation service."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution_job import ExecutionJob
from app.models.quality_gate import QualityGate, QualityGateResult

_JOB_GATE_STATUSES = {"succeeded", "failed", "timed_out"}


def normalize_gate_mode(mode: str | None) -> str:
    """读时归一化门禁模式：历史 block / 未知值一律视为 log，不写库、不迁移.

    本平台门禁为质量评估报表，不阻断执行；合法记录级别仅 warn / log。
    """
    return "warn" if mode == "warn" else "log"


def parse_gate_json(raw: str | None, default: Any = None) -> Any:
    """解析门禁规则或评估结果 JSON."""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def serialize_gate_json(value: Any) -> str:
    """将门禁规则或评估结果序列化为 JSON 字符串."""
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _coerce_number(value: Any) -> int | float | None:
    try:
        if value is None:
            return None
        return int(value) if isinstance(value, int) else float(value)
    except (TypeError, ValueError):
        return None


def derive_gate_metrics(metrics: dict[str, Any] | None) -> dict[str, Any]:
    """从任务结果指标派生质量门禁可用的通用指标。

    前端和门禁规则示例使用 0-1 比例的 pass_rate/error_rate，因此自动评估按比例
    提供 pass_rate 与 error_rate；同时保留原始 total/passed/failed/error 等字段。
    """
    source = dict(metrics or {})
    total = _coerce_number(source.get("total"))
    passed = _coerce_number(source.get("passed"))
    failed = _coerce_number(source.get("failed"))
    error = _coerce_number(source.get("error"))
    if total is not None and total > 0:
        source.setdefault(
            "pass_rate",
            round(float(passed or 0) / float(total), 6),
        )
        source.setdefault(
            "error_rate",
            round(
                (float(failed or 0) + float(error or 0)) / float(total),
                6,
            ),
        )
    return source


def evaluate_gate_rules(
    rules: list[dict[str, Any]] | None,
    metrics: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """评估门禁规则，返回 (是否全部通过, 各规则评估结果).

    兼容 `threshold` 与前端当前使用的 `value` 两种规则字段。
    """
    rule_results: list[dict[str, Any]] = []
    all_passed = True
    rules = rules or []

    op_funcs = {
        ">=": lambda a, b: a >= b,
        ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        "<": lambda a, b: a < b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
    }

    for rule in rules:
        if not isinstance(rule, dict):
            all_passed = False
            rule_results.append(
                {
                    "metric": None,
                    "op": None,
                    "threshold": None,
                    "actual": None,
                    "passed": False,
                    "reason": "门禁规则必须是 JSON 对象",
                }
            )
            continue
        metric = rule.get("metric")
        op = rule.get("op", ">=")
        threshold = rule.get("threshold", rule.get("value"))
        actual = metrics.get(metric) if metric else None

        passed = False
        if actual is None:
            reason = f"指标 '{metric}' 缺失"
        elif op not in op_funcs:
            reason = f"不支持的运算符 '{op}'"
        else:
            try:
                passed = bool(op_funcs[op](actual, threshold))
                reason = (
                    f"{metric}={actual} {op} {threshold}: "
                    f"{'通过' if passed else '未通过'}"
                )
            except TypeError:
                passed = False
                reason = f"指标 '{metric}' 类型不匹配：{actual} {op} {threshold}"

        if not passed:
            all_passed = False
        rule_results.append(
            {
                "metric": metric,
                "op": op,
                "threshold": threshold,
                "actual": actual,
                "passed": passed,
                "reason": reason,
            }
        )

    return all_passed, rule_results


def evaluate_job_quality_gates(
    db: Session,
    job: ExecutionJob,
    metrics: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """按任务所属项目自动评估启用的门禁，返回可写入 job 事件的摘要。

    调用方负责事务提交；评估异常不应中断主任务执行，因此本函数只返回当前可
    评估的项目门禁结果。
    """
    if not job.project_id or job.status not in _JOB_GATE_STATUSES:
        return []

    gates = list(
        db.execute(
            select(QualityGate).where(
                QualityGate.project_id == job.project_id,
                QualityGate.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    if not gates:
        return []

    gate_metrics = derive_gate_metrics(metrics)
    outcomes: list[dict[str, Any]] = []
    for gate in gates:
        rules = parse_gate_json(gate.rules, None)
        passed, rule_results = evaluate_gate_rules(rules, gate_metrics)
        result = QualityGateResult(
            gate_id=gate.id,
            project_id=job.project_id,
            run_id=job.id,
            passed=passed,
            results=serialize_gate_json(rule_results),
            triggered_by=f"job:{job.id[:28]}",
        )
        db.add(result)
        db.flush()
        outcomes.append(
            {
                "gate_id": gate.id,
                "gate_name": gate.name,
                "mode": normalize_gate_mode(gate.mode),
                "passed": passed,
                "result_id": result.id,
                "results": rule_results,
                "metrics": gate_metrics,
            }
        )
    return outcomes
