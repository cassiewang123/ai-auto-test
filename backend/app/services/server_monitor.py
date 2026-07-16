"""服务器监控采集服务（功能15）.

使用 psutil 采集 CPU / 内存 / 磁盘 IO / 网络流量，压测运行时每秒采样一次。
psutil 未安装时降级为零值采样，保证主流程不中断。
"""
from __future__ import annotations

import io
import re
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:  # 可选依赖
    import psutil

    _HAS_PSUTIL = True
except ImportError:  # pragma: no cover
    psutil = None
    _HAS_PSUTIL = False


@dataclass(slots=True)
class ServerConfig:
    """SSH connection settings for remote server metric collection."""

    host: str
    port: int = 22
    username: str = "root"
    password: str = ""
    key_path: str = ""
    key_string: str = ""


@dataclass(slots=True)
class ServerMetrics:
    """One remote server metric snapshot."""

    cpu_usage: float = 0.0
    mem_total_mb: int = 0
    mem_used_mb: int = 0
    mem_free_mb: int = 0
    disk_read_iops: float = 0.0
    disk_write_iops: float = 0.0
    net_rx_kb: float = 0.0
    net_tx_kb: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


class ServerMonitor:
    """Collect local metrics in a thread or remote metrics over SSH."""

    def __init__(self, test_id: str = "", run_id: str = ""):
        self.test_id = test_id
        self.run_id = run_id
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._prev_disk: Any = None
        self._prev_net: Any = None
        self._prev_ts: float | None = None
        self._start_ts: float | None = None
        self._client: Any = None

    def start(self) -> None:
        """启动后台采集线程."""
        if _HAS_PSUTIL:
            # 预热 CPU 采样（首次调用返回 0.0）
            with suppress(Exception):
                psutil.cpu_percent(interval=None)
        self._start_ts = time.time()
        self._thread = threading.Thread(target=self._sampling_loop, daemon=True)
        self._thread.start()

    def _sampling_loop(self) -> None:
        while not self._stop.is_set():
            with suppress(Exception):
                self._sample()
            self._stop.wait(1.0)

    def _sample(self) -> None:
        now = time.time()
        if self._start_ts is None:
            self._start_ts = now
        elapsed = now - self._start_ts

        cpu = 0.0
        mem = 0.0
        disk_read = disk_write = net_sent = net_recv = 0.0

        if _HAS_PSUTIL:
            try:
                cpu = float(psutil.cpu_percent(interval=None))
            except Exception:
                cpu = 0.0
            try:
                mem = float(psutil.virtual_memory().percent)
            except Exception:
                mem = 0.0
            try:
                disk = psutil.disk_io_counters()
            except Exception:
                disk = None
            try:
                net = psutil.net_io_counters()
            except Exception:
                net = None

            if self._prev_ts and disk and self._prev_disk:
                dt = max(0.001, now - self._prev_ts)
                disk_read = max(0.0, (disk.read_bytes - self._prev_disk.read_bytes) / 1024.0 / dt)
                disk_write = max(0.0, (disk.write_bytes - self._prev_disk.write_bytes) / 1024.0 / dt)
            if self._prev_ts and net and self._prev_net:
                dt = max(0.001, now - self._prev_ts)
                net_sent = max(0.0, (net.bytes_sent - self._prev_net.bytes_sent) / 1024.0 / dt)
                net_recv = max(0.0, (net.bytes_recv - self._prev_net.bytes_recv) / 1024.0 / dt)
            self._prev_disk = disk
            self._prev_net = net

        self._prev_ts = now
        self.samples.append({
            "elapsed": round(elapsed, 2),
            "timestamp": now,
            "cpu": round(cpu, 2),
            "memory": round(mem, 2),
            "disk_read": round(disk_read, 2),
            "disk_write": round(disk_write, 2),
            "net_sent": round(net_sent, 2),
            "net_recv": round(net_recv, 2),
        })

    def connect(self, config: ServerConfig) -> None:
        """Connect to a remote Linux server using password or RSA key auth."""
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict[str, Any] = {
            "hostname": config.host,
            "port": config.port,
            "username": config.username,
            "timeout": 10,
        }
        if config.key_path:
            kwargs["pkey"] = paramiko.RSAKey.from_private_key_file(config.key_path)
        elif config.key_string:
            kwargs["pkey"] = paramiko.RSAKey.from_private_key(
                io.StringIO(config.key_string)
            )
        elif config.password:
            kwargs["password"] = config.password
        client.connect(**kwargs)
        self._client = client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _run(self, command: str) -> str:
        if self._client is None:
            raise RuntimeError("SSH monitor is not connected")
        _, stdout, _ = self._client.exec_command(command, timeout=10)
        output = stdout.read()
        if isinstance(output, bytes):
            return output.decode("utf-8", errors="replace")
        return str(output)

    @staticmethod
    def _parse_cpu(raw: str) -> float:
        match = re.search(r"(\d+(?:\.\d+)?)\s*id\b", raw)
        return max(0.0, 100.0 - float(match.group(1))) if match else 0.0

    @staticmethod
    def _parse_memory(raw: str) -> dict[str, int]:
        match = re.search(
            r"^Mem:\s+(\d+)\s+(\d+)\s+(\d+)",
            raw,
            flags=re.MULTILINE,
        )
        if not match:
            return {"total": 0, "used": 0, "free": 0}
        return {
            "total": int(match.group(1)),
            "used": int(match.group(2)),
            "free": int(match.group(3)),
        }

    @staticmethod
    def _parse_disk_io(raw: str) -> dict[str, float]:
        read_iops = 0.0
        write_iops = 0.0
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) < 3 or not re.match(r"^[A-Za-z]", parts[0]):
                continue
            try:
                read_iops += float(parts[1])
                write_iops += float(parts[2])
            except ValueError:
                continue
        return {"read_iops": read_iops, "write_iops": write_iops}

    @staticmethod
    def _parse_network(raw: str) -> dict[str, float]:
        rx_bytes = 0
        tx_bytes = 0
        for line in raw.splitlines():
            if ":" not in line:
                continue
            interface, values = line.split(":", 1)
            if interface.strip() == "lo":
                continue
            parts = values.split()
            if len(parts) < 9:
                continue
            try:
                rx_bytes += int(parts[0])
                tx_bytes += int(parts[8])
            except ValueError:
                continue
        return {
            "rx_kb": rx_bytes / 1024.0,
            "tx_kb": tx_bytes / 1024.0,
        }

    def collect_metrics(self) -> ServerMetrics:
        """Collect one remote Linux metric snapshot."""
        cpu = self._parse_cpu(self._run("top -bn1"))
        memory = self._parse_memory(self._run("free -m"))
        disk = self._parse_disk_io(self._run("iostat -dx 1 1"))
        network = self._parse_network(self._run("cat /proc/net/dev"))
        return ServerMetrics(
            cpu_usage=cpu,
            mem_total_mb=memory["total"],
            mem_used_mb=memory["used"],
            mem_free_mb=memory["free"],
            disk_read_iops=disk["read_iops"],
            disk_write_iops=disk["write_iops"],
            net_rx_kb=network["rx_kb"],
            net_tx_kb=network["tx_kb"],
        )

    def stop(self) -> None:
        """停止采集线程并等待退出."""
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        # 再采最后一帧，确保覆盖压测尾声
        with suppress(Exception):
            self._sample()


def is_available() -> bool:
    """psutil 是否可用."""
    return _HAS_PSUTIL
