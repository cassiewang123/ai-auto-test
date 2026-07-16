"""Locust 压测引擎封装的单元测试.

覆盖：
- StressTestConfig / StressTestResult 模型
- 四种压测模式（constant/step/surge/soak）的命令行参数生成
- generate_locust_file：HttpUser 脚本生成（@task 权重、on_start 登录、wait_time、step shape）
- run_stress_test：mock subprocess，不依赖真实 locust 进程
- parse_locust_stats：解析 locust _stats.csv 文本
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.services.locust_runner import (
    LocustRunner,
    StressTestConfig,
    StressTestResult,
)


# ---------------------------------------------------------------------------
# 模型
# ---------------------------------------------------------------------------
class TestStressTestConfig:
    def test_default_mode_is_steady(self):
        config = StressTestConfig(users=100, spawn_rate=10, duration=60)
        assert config.mode == "steady"
        assert config.step_config is None

    def test_step_mode_with_step_config(self):
        step_config = {"stages": [{"users": 50, "spawn_rate": 5, "duration": 60}]}
        config = StressTestConfig(
            users=100, spawn_rate=10, duration=60, mode="step", step_config=step_config
        )
        assert config.mode == "step"
        assert config.step_config == step_config

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            StressTestConfig(users=1, spawn_rate=1, duration=1, mode="unknown")

    def test_negative_users_rejected(self):
        with pytest.raises(ValidationError):
            StressTestConfig(users=-1, spawn_rate=1, duration=1)


class TestStressTestResult:
    def test_result_defaults(self):
        result = StressTestResult(
            total_requests=100,
            total_failures=5,
            rps_avg=10.0,
            response_time_p50=42.0,
            response_time_p90=50.0,
            response_time_p99=65.0,
            error_rate=0.05,
            duration=60.0,
        )
        assert result.total_requests == 100
        assert result.error_rate == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 四种压测模式参数生成
# ---------------------------------------------------------------------------
class TestBuildModeArgs:
    def setup_method(self):
        self.runner = LocustRunner()

    def _arg(self, args, flag):
        return args[args.index(flag) + 1]

    def test_constant_mode(self):
        config = StressTestConfig(
            users=100, spawn_rate=10, duration=60, mode="constant"
        )
        args = self.runner.build_mode_args(config)
        assert self._arg(args, "-u") == "100"
        assert self._arg(args, "-r") == "10"
        assert self._arg(args, "-t") == "60"

    def test_surge_mode_uses_high_spawn_rate(self):
        # 突发峰值：spawn_rate 提升到 users，快速达到峰值
        config = StressTestConfig(users=200, spawn_rate=10, duration=30, mode="surge")
        args = self.runner.build_mode_args(config)
        assert self._arg(args, "-u") == "200"
        assert int(self._arg(args, "-r")) >= 200

    def test_soak_mode_extends_duration(self):
        # 长时间浸泡：至少 1 小时
        config = StressTestConfig(users=50, spawn_rate=5, duration=60, mode="soak")
        args = self.runner.build_mode_args(config)
        assert int(self._arg(args, "-t")) >= 3600

    def test_step_mode_uses_peak_users_and_total_duration(self):
        step_config = {
            "stages": [
                {"users": 50, "spawn_rate": 5, "duration": 60},
                {"users": 150, "spawn_rate": 10, "duration": 120},
                {"users": 80, "spawn_rate": 5, "duration": 60},
            ]
        }
        config = StressTestConfig(
            users=100, spawn_rate=10, duration=60, mode="step", step_config=step_config
        )
        args = self.runner.build_mode_args(config)
        assert self._arg(args, "-u") == "150"  # 峰值用户
        assert int(self._arg(args, "-t")) == 240  # 60+120+60

    def test_step_mode_without_step_config_falls_back_to_users(self):
        config = StressTestConfig(users=100, spawn_rate=10, duration=60, mode="step")
        args = self.runner.build_mode_args(config)
        assert self._arg(args, "-u") == "100"


# ---------------------------------------------------------------------------
# generate_locust_file
# ---------------------------------------------------------------------------
class TestGenerateLocustFile:
    def setup_method(self):
        self.runner = LocustRunner()

    def test_generates_http_user_class(self):
        config = StressTestConfig(users=10, spawn_rate=1, duration=10)
        cases = [{"name": "get_users", "method": "GET", "url": "/api/users", "weight": 2}]
        script = self.runner.generate_locust_file(cases, config)
        assert "HttpUser" in script
        assert "wait_time" in script

    def test_wait_time_from_config(self):
        config = StressTestConfig(
            users=10, spawn_rate=1, duration=10, wait_min=2, wait_max=5
        )
        cases = [{"name": "get_users", "method": "GET", "url": "/api/users", "weight": 1}]
        script = self.runner.generate_locust_file(cases, config)
        assert "between(2, 5)" in script

    def test_includes_tasks_with_weight(self):
        config = StressTestConfig(users=10, spawn_rate=1, duration=10)
        cases = [{"name": "get_users", "method": "GET", "url": "/api/users", "weight": 3}]
        script = self.runner.generate_locust_file(cases, config)
        assert "@task" in script
        assert "3" in script
        assert "/api/users" in script
        assert "GET" in script

    def test_post_body_serialized(self):
        config = StressTestConfig(users=10, spawn_rate=1, duration=10)
        cases = [
            {
                "name": "create_user",
                "method": "POST",
                "url": "/api/users",
                "weight": 1,
                "body": {"name": "alice", "age": 30},
            }
        ]
        script = self.runner.generate_locust_file(cases, config)
        assert "POST" in script
        assert "name" in script and "alice" in script

    def test_includes_on_start_login(self):
        config = StressTestConfig(users=10, spawn_rate=1, duration=10)
        cases = [
            {
                "name": "login",
                "method": "POST",
                "url": "/api/login",
                "is_login": True,
                "body": {"username": "admin", "password": "123"},
            },
            {"name": "get_users", "method": "GET", "url": "/api/users", "weight": 1},
        ]
        script = self.runner.generate_locust_file(cases, config)
        assert "on_start" in script
        assert "/api/login" in script

    def test_step_mode_includes_load_test_shape(self):
        step_config = {"stages": [{"users": 50, "spawn_rate": 5, "duration": 60}]}
        config = StressTestConfig(
            users=100, spawn_rate=10, duration=60, mode="step", step_config=step_config
        )
        cases = [{"name": "get_users", "method": "GET", "url": "/api/users", "weight": 1}]
        script = self.runner.generate_locust_file(cases, config)
        assert "LoadTestShape" in script
        assert "stages" in script

    def test_generated_script_is_importable_python(self):
        # 生成的脚本至少应当是语法合法的 Python
        config = StressTestConfig(users=10, spawn_rate=1, duration=10)
        cases = [
            {"name": "login", "method": "POST", "url": "/api/login", "is_login": True},
            {"name": "get_users", "method": "GET", "url": "/api/users", "weight": 1},
        ]
        script = self.runner.generate_locust_file(cases, config)
        compile(script, "<locustfile>", "exec")  # 不抛异常即通过


# ---------------------------------------------------------------------------
# parse_locust_stats
# ---------------------------------------------------------------------------
class TestParseLocustStats:
    def setup_method(self):
        self.runner = LocustRunner()
        # locust 2.x _stats.csv 的列结构
        self.csv_output = (
            "Type,Name,Request Count,Failure Count,Median Response Time,"
            "Average Response Time,Min Response Time,Max Response Time,"
            "Average Content Size,Requests/s,Failures/s,"
            "50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%\n"
            "GET,/api/users,100,5,42,45,12,203,1024,2.0,0.1,"
            "42,44,45,46,50,55,60,65,70,75,203\n"
            "None,Aggregated,100,5,42,45,12,203,1024,2.0,0.1,"
            "42,44,45,46,50,55,60,65,70,75,203\n"
        )

    def test_parses_aggregated_totals(self):
        parsed = self.runner.parse_locust_stats(self.csv_output)
        assert parsed["total_requests"] == 100
        assert parsed["total_failures"] == 5
        assert parsed["rps_avg"] == pytest.approx(2.0)

    def test_parses_percentiles(self):
        parsed = self.runner.parse_locust_stats(self.csv_output)
        assert parsed["response_time_p50"] == pytest.approx(42.0)
        assert parsed["response_time_p90"] == pytest.approx(50.0)
        assert parsed["response_time_p99"] == pytest.approx(65.0)

    def test_computes_error_rate(self):
        parsed = self.runner.parse_locust_stats(self.csv_output)
        assert parsed["error_rate"] == pytest.approx(0.05, abs=1e-6)

    def test_empty_output_returns_zeros(self):
        parsed = self.runner.parse_locust_stats("")
        assert parsed["total_requests"] == 0
        assert parsed["error_rate"] == 0.0


# ---------------------------------------------------------------------------
# run_stress_test (mock subprocess)
# ---------------------------------------------------------------------------
class TestRunStressTest:
    CSV_OUTPUT = (
        "Type,Name,Request Count,Failure Count,Median Response Time,"
        "Average Response Time,Min Response Time,Max Response Time,"
        "Average Content Size,Requests/s,Failures/s,"
        "50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%\n"
        "None,Aggregated,240,12,42,45,12,203,1024,4.0,0.2,"
        "42,44,45,46,50,55,60,65,70,75,203\n"
    )

    def test_run_returns_stress_test_result(self, tmp_path, monkeypatch):
        runner = LocustRunner()
        config = StressTestConfig(users=10, spawn_rate=1, duration=5)

        def fake_run(cmd, *args, **kwargs):
            # 把 --csv 指定的路径写出假统计文件
            csv_path = cmd[cmd.index("--csv") + 1]
            with open(csv_path, "w", encoding="utf-8") as fh:
                fh.write(self.CSV_OUTPUT)
            completed = MagicMock()
            completed.stdout = ""
            completed.returncode = 0
            return completed

        monkeypatch.setattr(subprocess, "run", fake_run)

        locust_file = tmp_path / "locustfile.py"
        locust_file.write_text("# fake", encoding="utf-8")

        result = runner.run_stress_test(str(locust_file), config)
        assert isinstance(result, StressTestResult)
        assert result.total_requests == 240
        assert result.total_failures == 12
        assert result.rps_avg == pytest.approx(4.0)
        assert result.error_rate == pytest.approx(0.05, abs=1e-6)

    def test_run_builds_headless_command(self, tmp_path, monkeypatch):
        runner = LocustRunner()
        config = StressTestConfig(users=20, spawn_rate=2, duration=10, mode="constant")
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            csv_path = cmd[cmd.index("--csv") + 1]
            with open(csv_path, "w", encoding="utf-8") as fh:
                fh.write(self.CSV_OUTPUT)
            completed = MagicMock()
            completed.stdout = ""
            completed.returncode = 0
            return completed

        monkeypatch.setattr(subprocess, "run", fake_run)
        locust_file = tmp_path / "locustfile.py"
        locust_file.write_text("# fake", encoding="utf-8")

        runner.run_stress_test(str(locust_file), config)
        cmd = captured["cmd"]
        assert cmd[0] == "locust"
        assert "-f" in cmd
        assert "--headless" in cmd
        assert "--csv" in cmd
        assert cmd[cmd.index("-u") + 1] == "20"
