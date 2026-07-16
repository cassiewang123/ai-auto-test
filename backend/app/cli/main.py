"""CLI 入口：ai-test 命令行工具。

子命令：
- run    执行测试计划（POST /api/v1/test-plans/{id}/run）
- stress 触发压测（POST /api/v1/test-plans/{id}/stress）
- report 获取测试报告（GET /api/v1/reports/{run_id}）

使用 click 解析参数、httpx 调用 API、rich 输出彩色结果。
"""
from __future__ import annotations

import click
import httpx
from rich.console import Console

DEFAULT_BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# 主命令组
# ---------------------------------------------------------------------------
@click.group()
@click.option(
    "--base-url",
    default=DEFAULT_BASE_URL,
    envvar="AI_TEST_BASE_URL",
    help="API 基础地址（默认 http://localhost:8000）",
)
@click.pass_context
def cli(ctx: click.Context, base_url: str) -> None:
    """AI 测试平台命令行工具。"""
    ctx.ensure_object(dict)
    ctx.obj["base_url"] = base_url.rstrip("/")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _console() -> Console:
    """创建 Console（在命令回调内调用，以捕获 CliRunner 的输出流）。"""
    return Console()


def _post(console: Console, url: str, payload: dict):
    """发起 POST 请求，异常时打印错误并返回 None。"""
    try:
        return httpx.post(url, json=payload, timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]请求失败:[/red] {exc}")
        return None


def _get(console: Console, url: str, params: dict | None = None):
    """发起 GET 请求，异常时打印错误并返回 None。"""
    try:
        return httpx.get(url, params=params, timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]请求失败:[/red] {exc}")
        return None


def _print_response(console: Console, resp, fmt: str = "json") -> None:
    """根据响应与格式打印结果。"""
    if resp.status_code >= 400:
        console.print(f"[red]请求失败 (HTTP {resp.status_code})[/red]")
    try:
        data = resp.json()
        if isinstance(data, str):
            console.print(data)
        else:
            console.print_json(data=data)
    except Exception:  # noqa: BLE001
        console.print(resp.text)


# ---------------------------------------------------------------------------
# run 子命令
# ---------------------------------------------------------------------------
@cli.command()
@click.option("--plan-id", required=True, help="测试计划 ID")
@click.option("--env", default=None, help="执行环境名称或 ID")
@click.option("--marker", default=None, help="用例标记筛选，如 smoke")
@click.option("--report-dir", default=None, help="报告输出目录")
@click.pass_context
def run(ctx: click.Context, plan_id: str, env: str | None, marker: str | None, report_dir: str | None) -> None:
    """执行测试计划。"""
    console = _console()
    base_url = ctx.obj["base_url"]
    url = f"{base_url}/api/v1/test-plans/{plan_id}/run"

    payload: dict = {}
    if env:
        payload["environment"] = env
    if marker:
        payload["marker"] = marker
    if report_dir:
        payload["report_dir"] = report_dir

    console.print(f"[cyan]触发测试计划执行:[/cyan] {plan_id}")
    resp = _post(console, url, payload)
    if resp is None:
        return
    _print_response(console, resp)


# ---------------------------------------------------------------------------
# stress 子命令
# ---------------------------------------------------------------------------
@cli.command()
@click.option("--plan-id", required=True, help="测试计划 ID")
@click.option("--users", default=1, type=int, help="并发用户数（默认 1）")
@click.option("--spawn-rate", default=1, type=float, help="每秒生成用户数（默认 1）")
@click.option("--duration", default="1m", help="压测时长，如 5m（默认 1m）")
@click.pass_context
def stress(
    ctx: click.Context,
    plan_id: str,
    users: int,
    spawn_rate: float,
    duration: str,
) -> None:
    """触发压测。"""
    console = _console()
    base_url = ctx.obj["base_url"]
    url = f"{base_url}/api/v1/test-plans/{plan_id}/stress"

    payload = {
        "users": users,
        "spawn_rate": spawn_rate,
        "duration": duration,
    }

    console.print(
        f"[cyan]触发压测:[/cyan] {plan_id} "
        f"(users={users}, spawn_rate={spawn_rate}, duration={duration})"
    )
    resp = _post(console, url, payload)
    if resp is None:
        return
    _print_response(console, resp)


# ---------------------------------------------------------------------------
# report 子命令
# ---------------------------------------------------------------------------
@cli.command()
@click.option("--run-id", required=True, help="执行批次 ID")
@click.option(
    "--format",
    "fmt",
    default="html",
    type=click.Choice(["html", "json"]),
    help="报告格式：html / json（默认 html）",
)
@click.pass_context
def report(ctx: click.Context, run_id: str, fmt: str) -> None:
    """获取测试报告。"""
    console = _console()
    base_url = ctx.obj["base_url"]
    url = f"{base_url}/api/v1/reports/{run_id}"

    console.print(f"[cyan]获取报告:[/cyan] run_id={run_id}, format={fmt}")
    resp = _get(console, url, params={"format": fmt})
    if resp is None:
        return

    if resp.status_code >= 400:
        console.print(f"[red]获取报告失败 (HTTP {resp.status_code})[/red]")
        try:
            console.print_json(data=resp.json())
        except Exception:  # noqa: BLE001
            console.print(resp.text)
        return

    if fmt == "html":
        console.print(resp.text)
    else:
        try:
            console.print_json(data=resp.json())
        except Exception:  # noqa: BLE001
            console.print(resp.text)


if __name__ == "__main__":
    cli()
