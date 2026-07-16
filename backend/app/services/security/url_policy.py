"""URL 出站策略：防止 SSRF 攻击.

对用户提供的 URL 执行出站安全校验：
    1. 仅允许 http/https 协议（拒绝 file://、ftp:// 等）
    2. 域名白名单 / 黑名单过滤
    3. DNS 解析后检查目标 IP，默认拒绝私有 / 环回 / 链路本地 / 组播地址
    4. 始终拒绝云元数据地址 169.254.169.254

开发环境可通过 ``allow_private=True`` 放行私有地址（如 127.0.0.1）。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class URLPolicy:
    """URL 出站安全策略校验器."""

    # 云元数据地址（始终拒绝，即使 allow_private=True）
    _CLOUD_METADATA_IP = "169.254.169.254"

    def __init__(
        self,
        allow_private: bool = False,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ):
        self.allow_private = allow_private
        self.allowed_domains = allowed_domains or []
        self.blocked_domains = blocked_domains or []

    def validate(self, url: str) -> tuple[bool, str]:
        """校验 URL 是否允许访问.

        Returns:
            (是否允许, 原因)。允许时原因为 "OK"。
        """
        # 1. 解析 URL
        parsed = urlparse(url)
        # 2. 仅允许 http/https
        if parsed.scheme not in ("http", "https"):
            return False, f"不允许的协议: {parsed.scheme}"
        # 3. 获取主机名
        hostname = parsed.hostname
        if not hostname:
            return False, "无效的 URL"
        # 4. 检查域名白/黑名单
        if self.allowed_domains and hostname not in self.allowed_domains:
            return False, f"域名不在白名单中: {hostname}"
        if hostname in self.blocked_domains:
            return False, f"域名在黑名单中: {hostname}"
        # 5. DNS 解析后检查 IP
        try:
            ips = socket.getaddrinfo(hostname, None)
            for family, _, _, _, sockaddr in ips:
                ip = ipaddress.ip_address(sockaddr[0])
                # 6. 默认拒绝 loopback/link-local/multicast/私有地址
                if not self.allow_private:
                    if (
                        ip.is_loopback
                        or ip.is_link_local
                        or ip.is_multicast
                        or ip.is_private
                    ):
                        # 允许 127.0.0.1 仅在开发模式
                        if ip.is_loopback and self.allow_private:
                            continue
                        return (
                            False,
                            f"不允许的目标地址: {ip} "
                            f"(私有/环回/链路本地/组播)",
                        )
                # 7. 拒绝云元数据地址 169.254.169.254
                if str(ip) == self._CLOUD_METADATA_IP:
                    return False, "不允许访问云元数据地址"
        except socket.gaierror:
            return False, f"DNS 解析失败: {hostname}"
        return True, "OK"
