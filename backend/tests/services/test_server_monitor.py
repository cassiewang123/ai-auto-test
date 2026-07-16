"""SSH 服务器监控服务单元测试.

解析函数（_parse_cpu / _parse_memory / _parse_disk_io）为纯函数，直接用
模拟的 top/free/iostat 输出字符串单测；connect/collect_metrics 用 mock
paramiko 与 mock _run，不依赖真实 SSH 服务。
"""
from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.services.server_monitor import (
    ServerConfig,
    ServerMetrics,
    ServerMonitor,
)


# ---------------------------------------------------------------------------
# 模型
# ---------------------------------------------------------------------------
class TestServerConfig:
    def test_defaults(self):
        config = ServerConfig(host="10.0.0.1")
        assert config.port == 22
        assert config.username == "root"
        assert config.password == ""
        assert config.key_path == ""
        assert config.key_string == ""

    def test_key_string(self):
        config = ServerConfig(host="h", key_string="-----BEGIN RSA...")
        assert config.key_string.startswith("-----BEGIN")


class TestServerMetrics:
    def test_defaults(self):
        m = ServerMetrics()
        assert m.cpu_usage == 0.0
        assert m.mem_total_mb == 0
        assert m.disk_read_iops == 0.0
        assert m.net_rx_kb == 0.0
        assert isinstance(m.timestamp, datetime)


# ---------------------------------------------------------------------------
# _parse_cpu（纯函数）
# ---------------------------------------------------------------------------
class TestParseCpu:
    def setup_method(self):
        self.monitor = ServerMonitor()

    def test_parse_from_top(self):
        raw = (
            "top - 10:00:00 up 1 day,  3:45,  2 users,  load average: 0.20, 0.18\n"
            "Tasks: 100 total,   1 running,  99 sleeping\n"
            "%Cpu(s):  5.0 us,  2.0 sy,  0.0 ni, 92.0 id,  1.0 wa,  0.0 hi,  0.0 si,  0.0 st\n"
        )
        assert self.monitor._parse_cpu(raw) == pytest.approx(8.0)

    def test_parse_high_load(self):
        raw = "%Cpu(s): 60.0 us, 20.0 sy,  0.0 ni, 18.0 id,  2.0 wa,  0.0 hi,  0.0 si,  0.0 st"
        assert self.monitor._parse_cpu(raw) == pytest.approx(82.0)

    def test_no_match_returns_zero(self):
        assert self.monitor._parse_cpu("no cpu info here") == 0.0


# ---------------------------------------------------------------------------
# _parse_memory（纯函数）
# ---------------------------------------------------------------------------
class TestParseMemory:
    def setup_method(self):
        self.monitor = ServerMonitor()

    def test_parse_from_free(self):
        raw = (
            "              total        used        free      shared  buff/cache   available\n"
            "Mem:           16384        8192        4096         256        4096       7680\n"
            "Swap:          2048           0        2048\n"
        )
        mem = self.monitor._parse_memory(raw)
        assert mem["total"] == 16384
        assert mem["used"] == 8192
        assert mem["free"] == 4096

    def test_no_match_returns_zeros(self):
        mem = self.monitor._parse_memory("nothing here")
        assert mem["total"] == 0
        assert mem["used"] == 0
        assert mem["free"] == 0


# ---------------------------------------------------------------------------
# _parse_disk_io（纯函数）
# ---------------------------------------------------------------------------
class TestParseDiskIO:
    def setup_method(self):
        self.monitor = ServerMonitor()

    def test_parse_from_iostat(self):
        raw = (
            "Linux 5.0.0 (host) \t01/01/2026 \t_x86_64_\t(4 CPU)\n"
            "\n"
            "Device     r/s     w/s     rkB/s     wkB/s   rrqm/s   wrqm/s  %util\n"
            "sda       10.00   20.00   100.00    200.00    0.00     0.00    5.00\n"
        )
        disk = self.monitor._parse_disk_io(raw)
        assert disk["read_iops"] == pytest.approx(10.0)
        assert disk["write_iops"] == pytest.approx(20.0)

    def test_no_match_returns_zeros(self):
        disk = self.monitor._parse_disk_io("no disk data")
        assert disk["read_iops"] == 0.0
        assert disk["write_iops"] == 0.0


# ---------------------------------------------------------------------------
# connect / close（mock paramiko）
# ---------------------------------------------------------------------------
class TestConnect:
    def test_connect_with_password(self, monkeypatch):
        fake_paramiko = MagicMock()
        fake_client = MagicMock()
        fake_paramiko.SSHClient.return_value = fake_client
        monkeypatch.setitem(sys.modules, "paramiko", fake_paramiko)

        monitor = ServerMonitor()
        config = ServerConfig(host="10.0.0.1", username="root", password="secret")
        monitor.connect(config)

        fake_paramiko.SSHClient.assert_called_once()
        fake_client.set_missing_host_key_policy.assert_called_once()
        fake_client.connect.assert_called_once()
        _, kwargs = fake_client.connect.call_args
        assert kwargs["hostname"] == "10.0.0.1"
        assert kwargs["password"] == "secret"
        assert monitor._client is fake_client

    def test_connect_with_key_path(self, monkeypatch):
        fake_paramiko = MagicMock()
        fake_client = MagicMock()
        fake_paramiko.SSHClient.return_value = fake_client
        monkeypatch.setitem(sys.modules, "paramiko", fake_paramiko)

        monitor = ServerMonitor()
        config = ServerConfig(host="h", username="u", key_path="/tmp/key")
        monitor.connect(config)
        _, kwargs = fake_client.connect.call_args
        assert "pkey" in kwargs
        fake_paramiko.RSAKey.from_private_key_file.assert_called_once_with("/tmp/key")

    def test_close(self):
        monitor = ServerMonitor()
        mock_client = MagicMock()
        monitor._client = mock_client
        monitor.close()
        mock_client.close.assert_called_once()
        assert monitor._client is None

    def test_close_when_not_connected(self):
        monitor = ServerMonitor()
        # 未连接时 close 不应报错
        monitor.close()
        assert monitor._client is None


# ---------------------------------------------------------------------------
# collect_metrics（mock _run）
# ---------------------------------------------------------------------------
class TestCollectMetrics:
    TOP_RAW = (
        "top - 10:00:00 up 1 day\n"
        "%Cpu(s):  5.0 us,  2.0 sy,  0.0 ni, 92.0 id,  1.0 wa\n"
    )
    MEM_RAW = (
        "              total        used        free\n"
        "Mem:           16384        8192        4096\n"
    )
    DISK_RAW = (
        "Device     r/s     w/s\n"
        "sda       10.00   20.00\n"
    )
    NET_RAW = (
        "Inter-|   Receive                                                |  Transmit\n"
        " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets\n"
        "  eth0: 1048576  2000    0    0    0     0          0         0  524288   1500\n"
    )

    def test_collect_metrics(self, monkeypatch):
        monitor = ServerMonitor()

        def fake_run(cmd):
            if "top" in cmd:
                return self.TOP_RAW
            if "free" in cmd:
                return self.MEM_RAW
            if "iostat" in cmd:
                return self.DISK_RAW
            if "/proc/net/dev" in cmd:
                return self.NET_RAW
            return ""

        monkeypatch.setattr(monitor, "_run", fake_run)
        metrics = monitor.collect_metrics()

        assert isinstance(metrics, ServerMetrics)
        assert metrics.cpu_usage == pytest.approx(8.0)
        assert metrics.mem_total_mb == 16384
        assert metrics.mem_used_mb == 8192
        assert metrics.mem_free_mb == 4096
        assert metrics.disk_read_iops == pytest.approx(10.0)
        assert metrics.disk_write_iops == pytest.approx(20.0)
        assert metrics.net_rx_kb == pytest.approx(1048576 / 1024)
        assert metrics.net_tx_kb == pytest.approx(524288 / 1024)
        assert isinstance(metrics.timestamp, datetime)
