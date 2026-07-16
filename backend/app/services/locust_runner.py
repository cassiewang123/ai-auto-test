"""Locust 压测引擎封装.

将接口用例定义转换为 Locust 脚本，并以无头（headless）方式驱动压测、
解析统计结果。Locust 本身通过 subprocess（CLI）调用，模块顶层不 import
locust，从而保证本模块在 locust 未安装时仍可被导入与单测。
"""
from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import tempfile
from typing import Any, Literal

from pydantic import BaseModel, Field


class StressTestConfig(BaseModel):
    """压测配置.

    mode 取值：
    - steady：稳定负载（恒定并发，等价 constant）
    - ramp：阶梯加压（从起始用户按步长分阶段递增到最大用户）
    - peak：峰值测试（快速冲顶保持后快速下降）
    - custom：自定义曲线（按 stages 数组执行）
    - constant/step/surge/soak：旧模式，保留向后兼容
    """

    users: int = Field(1, gt=0, description="并发用户数")
    spawn_rate: float = Field(1, gt=0, description="每秒启动用户数")
    duration: int = Field(60, gt=0, description="持续时间（秒）")
    mode: Literal[
        "steady", "ramp", "peak", "custom",
        "constant", "step", "surge", "soak",
    ] = "steady"
    step_config: dict[str, Any] | None = None
    # 功能14 新增模式配置
    ramp_config: dict[str, Any] | None = None  # {start_users, step, stage_duration, max_users}
    peak_config: dict[str, Any] | None = None  # {peak_users, hold_duration}
    custom_config: dict[str, Any] | None = None  # {stages: [{duration, users, spawn_rate}]}
    wait_min: float = Field(1.0, ge=0, description="请求间最小等待（秒）")
    wait_max: float = Field(3.0, ge=0, description="请求间最大等待（秒）")
    host: str = Field("", description="被测目标主机地址")


class StressTestResult(BaseModel):
    """压测结果汇总."""

    total_requests: int = 0
    total_failures: int = 0
    rps_avg: float = 0.0
    response_time_p50: float = 0.0
    response_time_p90: float = 0.0
    response_time_p99: float = 0.0
    error_rate: float = 0.0
    duration: float = 0.0


class LocustRunner:
    """Locust 压测运行器."""

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt(value: Any) -> str:
        """把数字格式化为字符串：整数浮点去掉小数点."""
        f = float(value)
        return str(int(f)) if f.is_integer() else str(f)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """转换为合法 Python 标识符."""
        cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", name or "")
        if cleaned and cleaned[0].isdigit():
            cleaned = "_" + cleaned
        return cleaned or "task"

    # ------------------------------------------------------------------
    # 阶段计算：将任意模式归一化为 stages 列表
    # ------------------------------------------------------------------
    def compute_stages(self, config: StressTestConfig) -> list[dict[str, Any]]:
        """将压测配置归一化为 stages 列表 [{duration, users, spawn_rate}].

        用于统一驱动 LoadTestShape 生成与 CLI 参数推导。
        """
        mode = config.mode
        # steady / constant：单一阶段恒定负载
        if mode in ("steady", "constant"):
            return [{
                "duration": config.duration,
                "users": config.users,
                "spawn_rate": config.spawn_rate,
            }]

        # ramp：阶梯加压，从 start_users 按步长递增到 max_users
        if mode == "ramp":
            rc = config.ramp_config or {}
            start_users = max(1, int(rc.get("start_users", 1)))
            max_users = max(start_users, int(rc.get("max_users", config.users)))
            step = max(1, int(rc.get("step", max(1, (max_users - start_users) // 4) or 1)))
            stage_duration = max(1, int(rc.get("stage_duration", config.duration // 4 or 1)))
            stages: list[dict[str, Any]] = []
            cur = start_users
            while cur <= max_users:
                stages.append({
                    "duration": stage_duration,
                    "users": cur,
                    "spawn_rate": config.spawn_rate,
                })
                if cur == max_users:
                    break
                cur = min(max_users, cur + step)
            return stages or [{
                "duration": config.duration, "users": config.users,
                "spawn_rate": config.spawn_rate,
            }]

        # peak：快速冲顶 -> 保持 -> 快速下降（三阶段）
        if mode == "peak":
            pc = config.peak_config or {}
            peak_users = max(1, int(pc.get("peak_users", config.users)))
            hold_duration = max(1, int(pc.get("hold_duration", config.duration // 2 or 1)))
            # 冲顶与下降各占剩余时长的一半（每段至少 1 秒）
            ramp_time = max(1, (config.duration - hold_duration) // 2)
            fast_rate = max(peak_users, config.spawn_rate)
            return [
                {"duration": ramp_time, "users": peak_users, "spawn_rate": fast_rate},
                {"duration": hold_duration, "users": peak_users, "spawn_rate": fast_rate},
                {"duration": ramp_time, "users": 0, "spawn_rate": fast_rate},
            ]

        # custom：直接使用 stages 数组
        if mode == "custom":
            stages = (config.custom_config or {}).get("stages") or []
            return [
                {
                    "duration": max(1, int(s.get("duration", 1))),
                    "users": max(0, int(s.get("users", 0))),
                    "spawn_rate": float(s.get("spawn_rate", config.spawn_rate)),
                }
                for s in stages
            ] or [{
                "duration": config.duration, "users": config.users,
                "spawn_rate": config.spawn_rate,
            }]

        # surge / soak / step：沿用旧逻辑
        if mode == "surge":
            surge_rate = max(config.users, config.spawn_rate)
            return [{
                "duration": config.duration, "users": config.users,
                "spawn_rate": surge_rate,
            }]
        if mode == "soak":
            return [{
                "duration": max(config.duration, 3600), "users": config.users,
                "spawn_rate": config.spawn_rate,
            }]
        if mode == "step":
            return [
                {
                    "duration": max(1, int(s["duration"])),
                    "users": max(0, int(s["users"])),
                    "spawn_rate": float(s.get("spawn_rate", config.spawn_rate)),
                }
                for s in ((config.step_config or {}).get("stages") or [])
            ] or [{
                "duration": config.duration, "users": config.users,
                "spawn_rate": config.spawn_rate,
            }]

        return [{
            "duration": config.duration, "users": config.users,
            "spawn_rate": config.spawn_rate,
        }]

    # ------------------------------------------------------------------
    # 压测模式的 CLI 参数生成
    # ------------------------------------------------------------------
    def build_mode_args(self, config: StressTestConfig) -> list[str]:
        """根据模式生成 locust 无头模式用户/速率/时长参数."""
        users = self._fmt(config.users)
        rate = self._fmt(config.spawn_rate)
        duration = self._fmt(config.duration)

        # 新模式统一通过 stages 推导峰值用户与总时长
        if config.mode in ("steady", "ramp", "peak", "custom"):
            stages = self.compute_stages(config)
            peak_users = max((s["users"] for s in stages), default=config.users)
            total_duration = sum(s["duration"] for s in stages)
            avg_spawn = (
                sum(s["spawn_rate"] for s in stages) / len(stages)
                if stages else config.spawn_rate
            )
            return [
                "-u", self._fmt(peak_users),
                "-r", self._fmt(avg_spawn),
                "-t", self._fmt(total_duration),
            ]

        if config.mode == "constant":
            return ["-u", users, "-r", rate, "-t", duration]

        if config.mode == "surge":
            # 突发峰值：spawn_rate 不低于 users，快速冲顶
            surge_rate = max(config.users, config.spawn_rate)
            return ["-u", users, "-r", self._fmt(surge_rate), "-t", duration]

        if config.mode == "soak":
            # 长时间浸泡：至少 1 小时
            soak_duration = max(config.duration, 3600)
            return ["-u", users, "-r", rate, "-t", self._fmt(soak_duration)]

        if config.mode == "step":
            stages = (config.step_config or {}).get("stages") or []
            if not stages:
                return ["-u", users, "-r", rate, "-t", duration]
            peak_users = max(s["users"] for s in stages)
            total_duration = sum(s["duration"] for s in stages)
            avg_spawn = sum(
                s.get("spawn_rate", config.spawn_rate) for s in stages
            ) / len(stages)
            return [
                "-u", self._fmt(peak_users),
                "-r", self._fmt(avg_spawn),
                "-t", self._fmt(total_duration),
            ]

        # 理论不可达（Literal 已约束）
        return ["-u", users, "-r", rate, "-t", duration]

    # ------------------------------------------------------------------
    # 脚本生成
    # ------------------------------------------------------------------
    def _build_request_line(self, case: dict) -> str:
        """构造单条 self.client.xxx(...) 调用语句."""
        method = str(case.get("method", "GET")).lower()
        parts: list[str] = [repr(case["url"])]
        if case.get("body"):
            parts.append(f"json={repr(case['body'])}")
        if case.get("headers"):
            parts.append(f"headers={repr(case['headers'])}")
        if case.get("params"):
            parts.append(f"params={repr(case['params'])}")
        return f"self.client.{method}({', '.join(parts)})"

    def generate_locust_file(
        self, test_cases: list[dict], config: StressTestConfig
    ) -> str:
        """将接口用例定义转换为 Locust HttpUser 脚本字符串.

        - is_login=True 的用例放入 on_start
        - 其余用例作为 @task(weight)
        - ramp/peak/custom/step 模式额外生成 LoadTestShape
        """
        # 多阶段模式需要 LoadTestShape 来动态调整并发
        need_shape = config.mode in ("ramp", "peak", "custom", "step")
        shape_stages: list[dict[str, Any]] = []
        if need_shape:
            shape_stages = self.compute_stages(config)
            # steady 等同 constant，无需 shape
            if config.mode == "step" and not (
                (config.step_config or {}).get("stages")
            ):
                need_shape = False
                shape_stages = []
            # 仅当阶段数 > 1 或单阶段也保留（custom 单阶段也允许）
            if not shape_stages:
                need_shape = False

        lines: list[str] = ["from locust import HttpUser, task, between"]
        if need_shape:
            lines.append("from locust import LoadTestShape")
        lines.append("")
        lines.append("")
        lines.append("class StressUser(HttpUser):")
        lines.append(
            f"    wait_time = between("
            f"{self._fmt(config.wait_min)}, {self._fmt(config.wait_max)})"
        )
        lines.append("")

        # on_start 登录
        login_cases = [c for c in test_cases if c.get("is_login")]
        if login_cases:
            lines.append("    def on_start(self):")
            for c in login_cases:
                lines.append(f"        {self._build_request_line(c)}")
            lines.append("")

        # 普通 task
        for case in test_cases:
            if case.get("is_login"):
                continue
            weight = case.get("weight", 1)
            method = str(case.get("method", "GET"))
            name = self._sanitize_name(case.get("name", "task"))
            lines.append(f"    # {method} {case['url']}")
            lines.append(f"    @task({self._fmt(weight)})")
            lines.append(f"    def {name}(self):")
            lines.append(f"        {self._build_request_line(case)}")
            lines.append("")

        # 多阶段 LoadTestShape（ramp/peak/custom/step 共用）
        if need_shape:
            lines.append("")
            lines.append("class StressShape(LoadTestShape):")
            lines.append("    stages = [")
            for s in shape_stages:
                stage_def = {
                    "duration": s["duration"],
                    "users": s["users"],
                    "spawn_rate": s["spawn_rate"],
                }
                lines.append(f"        {repr(stage_def)},")
            lines.append("    ]")
            lines.append("")
            lines.append("    def tick(self):")
            lines.append("        run_time = self.get_run_time()")
            lines.append("        for stage in self.stages:")
            lines.append("            if run_time < stage['duration']:")
            lines.append("                return (stage['users'], stage['spawn_rate'])")
            lines.append("            run_time -= stage['duration']")
            lines.append("        return None")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 统计解析
    # ------------------------------------------------------------------
    def parse_locust_stats(self, stats_output: str) -> dict:
        """解析 locust _stats.csv 文本，提取 Aggregated 聚合统计."""
        result: dict[str, Any] = {
            "total_requests": 0,
            "total_failures": 0,
            "rps_avg": 0.0,
            "response_time_p50": 0.0,
            "response_time_p90": 0.0,
            "response_time_p99": 0.0,
            "error_rate": 0.0,
        }
        if not stats_output or not stats_output.strip():
            return result

        reader = csv.DictReader(io.StringIO(stats_output))
        for row in reader:
            if (row.get("Name") or "").strip() != "Aggregated":
                continue
            result["total_requests"] = int(float(row.get("Request Count", 0) or 0))
            result["total_failures"] = int(float(row.get("Failure Count", 0) or 0))
            result["rps_avg"] = float(row.get("Requests/s", 0) or 0)
            result["response_time_p50"] = float(row.get("50%", 0) or 0)
            result["response_time_p90"] = float(row.get("90%", 0) or 0)
            result["response_time_p99"] = float(row.get("99%", 0) or 0)
            total = result["total_requests"]
            result["error_rate"] = (
                result["total_failures"] / total if total > 0 else 0.0
            )
            break
        return result

    # ------------------------------------------------------------------
    # 执行压测
    # ------------------------------------------------------------------
    def run_stress_test(
        self, locust_file_path: str, config: StressTestConfig
    ) -> StressTestResult:
        """以无头模式调用 locust CLI 执行压测并返回汇总结果.

        外部依赖 locust 通过 subprocess 调用，便于在测试中 mock。
        """
        stats_path = tempfile.mktemp(suffix="_stats.csv")

        cmd: list[str] = [
            "locust", "-f", locust_file_path, "--headless",
        ]
        if config.host:
            cmd += ["--host", config.host]
        cmd += self.build_mode_args(config)
        cmd += ["--csv", stats_path]

        completed = subprocess.run(cmd, capture_output=True, text=True)

        stats_output = ""
        try:
            with open(stats_path, encoding="utf-8") as fh:
                stats_output = fh.read()
        except FileNotFoundError:
            stats_output = completed.stdout or ""
        finally:
            try:
                os.remove(stats_path)
            except OSError:
                pass

        parsed = self.parse_locust_stats(stats_output)
        return StressTestResult(
            total_requests=parsed["total_requests"],
            total_failures=parsed["total_failures"],
            rps_avg=parsed["rps_avg"],
            response_time_p50=parsed["response_time_p50"],
            response_time_p90=parsed["response_time_p90"],
            response_time_p99=parsed["response_time_p99"],
            error_rate=parsed["error_rate"],
            duration=float(config.duration),
        )
