"""CLI 工具测试。

使用 click 的 CliRunner 测试各子命令，mock httpx 调用，
验证命令行参数解析与 API 调用正确，不依赖真实 API 服务。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from app.cli.main import cli


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# run 子命令
# ---------------------------------------------------------------------------
class TestRunCommand:
    def test_basic(self):
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.post.return_value = _mock_response(
                json_data={"code": 0, "data": {"run_id": "run-123"}}
            )
            result = runner.invoke(
                cli,
                ["run", "--plan-id", "plan-1"],
            )
        assert result.exit_code == 0
        mock_httpx.post.assert_called_once()
        # 验证 URL
        call_args = mock_httpx.post.call_args
        assert "/api/v1/test-plans/plan-1/run" in str(call_args)

    def test_all_options(self):
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.post.return_value = _mock_response(
                json_data={"code": 0, "data": {"run_id": "run-1"}}
            )
            result = runner.invoke(
                cli,
                [
                    "run",
                    "--plan-id",
                    "plan-1",
                    "--env",
                    "dev",
                    "--marker",
                    "smoke",
                    "--report-dir",
                    "/tmp/reports",
                ],
            )
        assert result.exit_code == 0
        call_args = mock_httpx.post.call_args
        # 验证 URL
        assert "/api/v1/test-plans/plan-1/run" in str(call_args)
        # 验证 payload 包含各选项
        payload = call_args.kwargs.get("json", {})
        assert payload.get("environment") == "dev"
        assert payload.get("marker") == "smoke"
        assert payload.get("report_dir") == "/tmp/reports"

    def test_missing_plan_id(self):
        """缺少必填参数 --plan-id 时退出码非 0。"""
        runner = CliRunner()
        result = runner.invoke(cli, ["run"])
        assert result.exit_code != 0

    def test_base_url_option(self):
        """--base-url 改变请求目标。"""
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.post.return_value = _mock_response(json_data={"code": 0})
            result = runner.invoke(
                cli,
                ["--base-url", "http://api.example.com:9000", "run", "--plan-id", "p1"],
            )
        assert result.exit_code == 0
        call_args = mock_httpx.post.call_args
        assert "http://api.example.com:9000" in str(call_args)

    def test_api_error_handled(self):
        """API 返回错误时优雅处理（非崩溃）。"""
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.post.return_value = _mock_response(
                status_code=500, json_data={"code": -1, "message": "server error"}
            )
            result = runner.invoke(
                cli, ["run", "--plan-id", "p1"]
            )
        # 应优雅退出，不抛异常
        assert result.exit_code == 0

    def test_request_exception_handled(self):
        """网络异常时优雅处理。"""
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("connection refused")
            result = runner.invoke(
                cli, ["run", "--plan-id", "p1"]
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# stress 子命令
# ---------------------------------------------------------------------------
class TestStressCommand:
    def test_basic(self):
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.post.return_value = _mock_response(
                json_data={"code": 0, "data": {"run_id": "stress-1"}}
            )
            result = runner.invoke(
                cli,
                [
                    "stress",
                    "--plan-id",
                    "plan-1",
                    "--users",
                    "100",
                    "--spawn-rate",
                    "10",
                    "--duration",
                    "5m",
                ],
            )
        assert result.exit_code == 0
        mock_httpx.post.assert_called_once()
        call_args = mock_httpx.post.call_args
        assert "/api/v1/test-plans/plan-1/stress" in str(call_args)
        payload = call_args.kwargs.get("json", {})
        assert payload.get("users") == 100
        assert payload.get("spawn_rate") == 10
        assert payload.get("duration") == "5m"

    def test_default_values(self):
        """未提供可选参数时使用默认值。"""
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.post.return_value = _mock_response(json_data={"code": 0})
            result = runner.invoke(cli, ["stress", "--plan-id", "p1"])
        assert result.exit_code == 0
        payload = mock_httpx.post.call_args.kwargs.get("json", {})
        assert "users" in payload

    def test_missing_plan_id(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["stress"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# report 子命令
# ---------------------------------------------------------------------------
class TestReportCommand:
    def test_json_format(self):
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.get.return_value = _mock_response(
                json_data={"code": 0, "data": {"summary": "passed"}}
            )
            result = runner.invoke(
                cli, ["report", "--run-id", "run-1", "--format", "json"]
            )
        assert result.exit_code == 0
        mock_httpx.get.assert_called_once()
        call_args = mock_httpx.get.call_args
        assert "/api/v1/reports/run-1" in str(call_args)

    def test_html_format(self):
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.get.return_value = _mock_response(
                text="<html>report</html>"
            )
            result = runner.invoke(
                cli, ["report", "--run-id", "run-1", "--format", "html"]
            )
        assert result.exit_code == 0
        call_args = mock_httpx.get.call_args
        assert "/api/v1/reports/run-1" in str(call_args)

    def test_default_format(self):
        """默认格式为 html。"""
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.get.return_value = _mock_response(text="<html></html>")
            result = runner.invoke(cli, ["report", "--run-id", "run-1"])
        assert result.exit_code == 0
        mock_httpx.get.assert_called_once()

    def test_missing_run_id(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["report"])
        assert result.exit_code != 0

    def test_request_exception_handled(self):
        runner = CliRunner()
        with patch("app.cli.main.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("timeout")
            result = runner.invoke(cli, ["report", "--run-id", "run-1"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 主命令组
# ---------------------------------------------------------------------------
class TestCliGroup:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "stress" in result.output
        assert "report" in result.output

    def test_subcommand_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--plan-id" in result.output
        assert "--env" in result.output
        assert "--marker" in result.output
        assert "--report-dir" in result.output

    def test_stress_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["stress", "--help"])
        assert result.exit_code == 0
        assert "--users" in result.output
        assert "--spawn-rate" in result.output
        assert "--duration" in result.output

    def test_report_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--help"])
        assert result.exit_code == 0
        assert "--run-id" in result.output
        assert "--format" in result.output
