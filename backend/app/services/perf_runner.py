"""压测执行服务（功能14/15/16/17 核心逻辑）.

将原 run 端点的执行逻辑重构为可在后台线程运行的服务函数，支持：
- 多种压测模式（steady/ramp/peak/custom）按 stages 分阶段调度并发
- 服务器监控采集（ServerMonitor，每秒一帧）
- 实时指标快照写入内存存储（供 /realtime 轮询）
- 压测结束自动评估 SLA 阈值
- 持久化 PerformanceResult 与 PerfMetric 记录
"""
from __future__ import annotations

import threading
import time
import uuid as _uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.perf_metric import PerfMetric
from app.models.performance_result import PerformanceResult
from app.models.performance_test import PerformanceTest
from app.models.test_case import TestCase
from app.services import perf_realtime
from app.services.locust_runner import LocustRunner, StressTestConfig
from app.services.server_monitor import ServerMonitor


def _percentile(sorted_values: list[float], pct: float) -> float:
    """计算分位数（pct 为 0-100）."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def _build_request_def_from_case(case: TestCase):
    """从 TestCase 模型构建 RequestDefinition（避免在子线程访问 ORM session）."""
    from app.schemas.execution import RequestDefinition  # noqa: E402

    return RequestDefinition(
        method=case.method,
        url=case.url,
        headers=dict(case.headers or {}),
        params=dict(case.params or {}),
        body=case.body,
        graphql_query=case.graphql_query,
        files=list(case.files) if case.files else None,
        extract_rules=list(case.extract_rules or []),
        timeout=30.0,
    )


def _build_stress_config(test_config: dict[str, Any]) -> StressTestConfig:
    """从前端 config JSON 构建 StressTestConfig."""
    mode = str(test_config.get("mode", "steady") or "steady")
    users = int(test_config.get("users", 1) or 1)
    spawn_rate = float(test_config.get("spawn_rate", 1) or 1)
    duration = int(test_config.get("duration", 10) or 10)

    kwargs: dict[str, Any] = {
        "users": users,
        "spawn_rate": spawn_rate,
        "duration": duration,
        "mode": mode,  # type: ignore[arg-type]
    }
    if mode == "ramp":
        kwargs["ramp_config"] = test_config.get("ramp_config") or {}
    elif mode == "peak":
        kwargs["peak_config"] = test_config.get("peak_config") or {}
    elif mode == "custom":
        kwargs["custom_config"] = test_config.get("custom_config") or {}
    return StressTestConfig(**kwargs)


def _evaluate_sla(
    sla_cfg: dict[str, Any] | None,
    p95: float,
    error_rate_pct: float,
    rps: float,
) -> tuple[str | None, dict[str, Any]]:
    """评估 SLA 阈值，返回 (sla_status, sla_details).

    sla_cfg: {response_time_p95: ms, error_rate: 0-1 分数, rps_min: 数值}
    """
    if not sla_cfg:
        return None, {}

    p95_th = sla_cfg.get("response_time_p95")
    err_th = sla_cfg.get("error_rate")
    rps_min = sla_cfg.get("rps_min")

    details: dict[str, Any] = {}
    checks: list[str] = []  # 各项状态：pass/fail/warning

    if p95_th is not None:
        p95_th = float(p95_th)
        val = p95
        status = "pass"
        if val > p95_th:
            status = "fail"
        elif p95_th > 0 and val > 0.9 * p95_th:
            status = "warning"
        checks.append(status)
        details["response_time_p95"] = {
            "threshold": p95_th, "actual": round(val, 2), "status": status,
        }

    if err_th is not None:
        err_th = float(err_th)
        # error_rate_pct 后端存储为百分数（0-100），阈值 err_th 为 0-1 分数
        actual_frac = error_rate_pct / 100.0
        status = "pass"
        if actual_frac > err_th:
            status = "fail"
        elif err_th > 0 and actual_frac > 0.9 * err_th:
            status = "warning"
        checks.append(status)
        details["error_rate"] = {
            "threshold": err_th, "actual": round(actual_frac, 4), "status": status,
        }

    if rps_min is not None:
        rps_min = float(rps_min)
        status = "pass"
        if rps < rps_min:
            status = "fail"
        elif rps_min > 0 and rps < 1.1 * rps_min:
            status = "warning"
        checks.append(status)
        details["rps_min"] = {
            "threshold": rps_min, "actual": round(rps, 2), "status": status,
        }

    if not checks:
        return None, {}

    if "fail" in checks:
        overall = "failed"
    elif "warning" in checks:
        overall = "warning"
    else:
        overall = "passed"
    return overall, details


def execute_performance_test(test_id: str, run_id: str | None = None) -> str:
    """在调用方线程中执行压测（建议由后台线程调用）。

    返回 run_id。执行过程中更新 perf_realtime 内存存储；结束后持久化结果与监控指标。
    """
    if run_id is None:
        run_id = str(_uuid.uuid4())
    perf_realtime.init_run(test_id, run_id)

    db: Session = SessionLocal()
    try:
        test = db.get(PerformanceTest, test_id)
        if not test:
            perf_realtime.set_status(test_id, "failed", error="压测场景不存在")
            return run_id

        test_config = test.config or {}
        mode = str(test_config.get("mode", "steady") or "steady")
        stress_config = _build_stress_config(test_config)
        stages = LocustRunner().compute_stages(stress_config)

        # 限制总时长，防止资源耗尽
        capped_stages: list[dict[str, Any]] = []
        total_dur = 0
        for s in stages:
            d = max(1, min(int(s["duration"]), 600))
            u = max(0, min(int(s["users"]), 200))
            capped_stages.append({
                "duration": d, "users": u,
                "spawn_rate": float(s.get("spawn_rate", stress_config.spawn_rate) or 1),
            })
            total_dur += d
        total_dur = min(total_dur, 600)

        # 获取关联用例
        case_ids = test.case_ids or []
        if not case_ids:
            test.status = "failed"
            db.commit()
            perf_realtime.set_status(test_id, "failed", error="没有关联的测试用例")
            return run_id
        cases: list[TestCase] = [c for c in (db.get(TestCase, cid) for cid in case_ids) if c]
        if not cases:
            test.status = "failed"
            db.commit()
            perf_realtime.set_status(test_id, "failed", error="关联的测试用例均不存在")
            return run_id

        request_defs = [
            (_build_request_def_from_case(c), [a.__dict__ for a in c.assertions], c.id, c.title)
            for c in cases
        ]

        # 更新状态为 running
        test.status = "running"
        db.commit()

        # 共享计数器（线程安全）
        lock = threading.Lock()
        all_response_times: list[float] = []
        recent_times: deque[float] = deque(maxlen=500)
        counters = {"success": 0, "fail": 0}
        detail_stats: dict[str, Any] = {}
        for _, _, cid, title in request_defs:
            detail_stats[cid] = {
                "title": title, "count": 0, "success": 0, "fail": 0,
                "response_times": [],
            }

        from test_engine.executor import TestCaseExecutor
        executor_instance = TestCaseExecutor()

        def _worker(user_index: int, deadline_ts: float) -> None:
            """单个虚拟用户在当前阶段内循环执行用例。"""
            idx = user_index % len(request_defs)
            while time.perf_counter() < deadline_ts:
                req_def, assertions, cid, _ = request_defs[idx]
                try:
                    result = executor_instance.execute(
                        request_def=req_def, assertions=assertions, variables={},
                    )
                    rt = result.duration
                    with lock:
                        all_response_times.append(rt)
                        recent_times.append(rt)
                        if result.status == "passed":
                            counters["success"] += 1
                            detail_stats[cid]["success"] += 1
                        else:
                            counters["fail"] += 1
                            detail_stats[cid]["fail"] += 1
                        detail_stats[cid]["count"] += 1
                        detail_stats[cid]["response_times"].append(rt)
                except Exception:
                    with lock:
                        counters["fail"] += 1
                        detail_stats[cid]["count"] += 1
                        detail_stats[cid]["fail"] += 1
                idx = (idx + 1) % len(request_defs)

        # 启动服务器监控
        monitor = ServerMonitor(test_id, run_id)
        monitor.start()

        # 实时快照采集线程
        snapshot_stop = threading.Event()
        prev_total = 0
        start_ts = time.perf_counter()

        def _snapshot_loop() -> None:
            nonlocal prev_total
            while not snapshot_stop.is_set():
                with lock:
                    total = counters["success"] + counters["fail"]
                    fail = counters["fail"]
                    rt_avg = (sum(recent_times) / len(recent_times)) if recent_times else 0.0
                rps_inst = total - prev_total
                prev_total = total
                elapsed = time.perf_counter() - start_ts
                err_rate = (fail / total * 100.0) if total > 0 else 0.0
                perf_realtime.append_snapshot(test_id, {
                    "t": round(elapsed, 2),
                    "rps": rps_inst,
                    "avg_rt": round(rt_avg, 2),
                    "error_rate": round(err_rate, 2),
                    "active_users": _current_active_users,
                    "total_requests": total,
                    "fail_requests": fail,
                })
                snapshot_stop.wait(1.0)

        _current_active_users = 0
        snap_thread = threading.Thread(target=_snapshot_loop, daemon=True)
        snap_thread.start()

        # 按 stages 顺序执行
        try:
            for stage in capped_stages:
                stage_users = stage["users"]
                stage_duration = stage["duration"]
                stage_spawn = max(1.0, stage["spawn_rate"])
                if stage_users <= 0:
                    # 峰值下降阶段：无活跃用户，仅等待
                    _current_active_users = 0
                    time.sleep(stage_duration)
                    continue
                _current_active_users = stage_users
                max_workers = min(stage_users, 50)
                stage_deadline = time.perf_counter() + stage_duration
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    spawned = 0
                    futures = []
                    while spawned < stage_users:
                        batch = min(int(stage_spawn), stage_users - spawned)
                        if batch <= 0:
                            batch = 1
                        for _ in range(batch):
                            futures.append(pool.submit(_worker, spawned, stage_deadline))
                            spawned += 1
                        if spawned < stage_users:
                            time.sleep(1.0)
                    for fut in futures:
                        try:
                            fut.result()
                        except Exception:
                            with lock:
                                counters["fail"] += 1
        except Exception:
            pass
        finally:
            snapshot_stop.set()
            snap_thread.join(timeout=2.0)
            monitor.stop()

        elapsed = time.perf_counter() - start_ts

        # 计算统计指标
        with lock:
            all_success = counters["success"]
            all_fail = counters["fail"]
            local_times = list(all_response_times)

        total_requests = all_success + all_fail
        sorted_times = sorted(local_times)
        avg_rt = (sum(local_times) / len(local_times)) if local_times else 0.0
        min_rt = sorted_times[0] if sorted_times else 0.0
        max_rt = sorted_times[-1] if sorted_times else 0.0
        p50 = _percentile(sorted_times, 50)
        p90 = _percentile(sorted_times, 90)
        p95 = _percentile(sorted_times, 95)
        p99 = _percentile(sorted_times, 99)
        rps = (total_requests / elapsed) if elapsed > 0 else 0.0
        error_rate = (all_fail / total_requests * 100.0) if total_requests > 0 else 0.0

        # 聚合 detail
        detail_output: dict[str, Any] = {}
        for cid, stats in detail_stats.items():
            rt_list = stats.get("response_times", [])
            detail_output[cid] = {
                "title": stats.get("title", ""),
                "count": stats.get("count", 0),
                "success": stats.get("success", 0),
                "fail": stats.get("fail", 0),
                "avg_response_time": (sum(rt_list) / len(rt_list)) if rt_list else 0.0,
                "min_response_time": min(rt_list) if rt_list else 0.0,
                "max_response_time": max(rt_list) if rt_list else 0.0,
            }

        # SLA 评估（功能16）
        sla_cfg = test_config.get("sla") if isinstance(test_config.get("sla"), dict) else None
        sla_status, sla_details = _evaluate_sla(sla_cfg, p95, error_rate, rps)

        result = PerformanceResult(
            test_id=test_id,
            run_id=run_id,
            total_requests=total_requests,
            success_requests=all_success,
            fail_requests=all_fail,
            avg_response_time=round(avg_rt, 4),
            min_response_time=round(min_rt, 4),
            max_response_time=round(max_rt, 4),
            p50=round(p50, 4),
            p90=round(p90, 4),
            p95=round(p95, 4),
            p99=round(p99, 4),
            rps=round(rps, 2),
            error_rate=round(error_rate, 2),
            duration=round(elapsed, 2),
            detail=detail_output,
            sla_status=sla_status,
            sla_details=sla_details,
            mode=mode,
        )
        db.add(result)
        db.flush()  # 获取 result.id

        # 持久化服务器监控指标（功能15）
        for sample in monitor.samples:
            db.add(PerfMetric(
                test_id=test_id,
                run_id=run_id,
                result_id=result.id,
                elapsed=sample["elapsed"],
                cpu=sample["cpu"],
                memory=sample["memory"],
                disk_read=sample["disk_read"],
                disk_write=sample["disk_write"],
                net_sent=sample["net_sent"],
                net_recv=sample["net_recv"],
            ))

        # 更新压测场景状态
        test.status = "completed" if all_success > 0 or all_fail == 0 else (
            "completed" if total_requests > 0 else "failed"
        )
        test.last_run_at = datetime.now()
        db.commit()
        db.refresh(result)

        perf_realtime.set_status(test_id, "completed", result_id=result.id)
        return run_id
    except Exception as exc:  # noqa: BLE001
        try:
            test = db.get(PerformanceTest, test_id)
            if test:
                test.status = "failed"
                db.commit()
        except Exception:
            pass
        perf_realtime.set_status(test_id, "failed", error=str(exc))
        return run_id
    finally:
        db.close()


def run_in_background(test_id: str) -> str:
    """在后台守护线程中启动压测，立即返回 run_id。"""
    run_id = str(_uuid.uuid4())
    perf_realtime.init_run(test_id, run_id)

    def _bg() -> None:
        try:
            execute_performance_test(test_id, run_id=run_id)
        except Exception as exc:  # noqa: BLE001
            perf_realtime.set_status(test_id, "failed", error=str(exc))

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()
    return run_id
