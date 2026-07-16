"""URLPolicy 单元测试：SSRF 防护出站策略校验."""
from __future__ import annotations

import pytest

from app.services.security.url_policy import URLPolicy


# ---------------------------------------------------------------------------
# 协议校验
# ---------------------------------------------------------------------------
class TestProtocolValidation:
    def test_rejects_file_protocol(self):
        policy = URLPolicy(allow_private=True)
        ok, reason = policy.validate("file:///etc/passwd")
        assert ok is False
        assert "不允许的协议" in reason

    def test_rejects_ftp_protocol(self):
        policy = URLPolicy(allow_private=True)
        ok, reason = policy.validate("ftp://example.com/file")
        assert ok is False
        assert "不允许的协议" in reason

    def test_rejects_empty_scheme(self):
        policy = URLPolicy(allow_private=True)
        ok, reason = policy.validate("not-a-url")
        assert ok is False

    def test_allows_http(self):
        policy = URLPolicy(allow_private=True)
        ok, _ = policy.validate("http://127.0.0.1:8000/")
        assert ok is True

    def test_allows_https(self):
        policy = URLPolicy(allow_private=True)
        ok, _ = policy.validate("https://127.0.0.1:8000/")
        assert ok is True


# ---------------------------------------------------------------------------
# 无效 URL
# ---------------------------------------------------------------------------
class TestInvalidUrl:
    def test_rejects_missing_hostname(self):
        policy = URLPolicy(allow_private=True)
        ok, reason = policy.validate("http://")
        assert ok is False
        assert "无效" in reason or "DNS" in reason


# ---------------------------------------------------------------------------
# 私有 / 环回 / 链路本地地址
# ---------------------------------------------------------------------------
class TestPrivateAddressBlocking:
    def test_rejects_localhost_when_not_allowed(self):
        policy = URLPolicy(allow_private=False)
        ok, reason = policy.validate("http://localhost/")
        assert ok is False
        assert "不允许" in reason

    def test_rejects_loopback_ip_when_not_allowed(self):
        policy = URLPolicy(allow_private=False)
        ok, reason = policy.validate("http://127.0.0.1/")
        assert ok is False
        assert "不允许" in reason

    def test_allows_loopback_when_allow_private(self):
        policy = URLPolicy(allow_private=True)
        ok, _ = policy.validate("http://127.0.0.1:8000/")
        assert ok is True

    def test_allows_localhost_when_allow_private(self):
        policy = URLPolicy(allow_private=True)
        ok, _ = policy.validate("http://localhost:3000/")
        assert ok is True


# ---------------------------------------------------------------------------
# 云元数据地址（始终拒绝）
# ---------------------------------------------------------------------------
class TestCloudMetadataBlocking:
    def test_rejects_aws_metadata(self):
        policy = URLPolicy(allow_private=True)
        ok, reason = policy.validate("http://169.254.169.254/latest/meta-data/")
        assert ok is False
        assert "元数据" in reason

    def test_rejects_aws_metadata_even_strict(self):
        policy = URLPolicy(allow_private=False)
        ok, reason = policy.validate("http://169.254.169.254/")
        assert ok is False


# ---------------------------------------------------------------------------
# 域名白名单
# ---------------------------------------------------------------------------
class TestAllowedDomains:
    def test_rejects_domain_not_in_whitelist(self):
        policy = URLPolicy(
            allow_private=True,
            allowed_domains=["allowed.example"],
        )
        ok, reason = policy.validate("http://blocked.example/")
        assert ok is False
        assert "白名单" in reason

    def test_allows_domain_in_whitelist(self):
        policy = URLPolicy(
            allow_private=True,
            allowed_domains=["127.0.0.1"],
        )
        ok, _ = policy.validate("http://127.0.0.1:8000/")
        assert ok is True


# ---------------------------------------------------------------------------
# 域名黑名单
# ---------------------------------------------------------------------------
class TestBlockedDomains:
    def test_rejects_blocked_domain(self):
        policy = URLPolicy(
            allow_private=True,
            blocked_domains=["169.254.169.254"],
        )
        ok, reason = policy.validate("http://169.254.169.254/")
        assert ok is False
        assert "黑名单" in reason or "元数据" in reason


# ---------------------------------------------------------------------------
# DNS 解析失败
# ---------------------------------------------------------------------------
class TestDnsFailure:
    def test_rejects_unresolvable_domain(self):
        policy = URLPolicy(allow_private=True)
        ok, reason = policy.validate(
            "http://this-domain-definitely-does-not-exist-xyz.invalid/"
        )
        assert ok is False
        assert "DNS" in reason


# ---------------------------------------------------------------------------
# 返回值结构
# ---------------------------------------------------------------------------
class TestReturnValue:
    def test_returns_tuple_on_success(self):
        policy = URLPolicy(allow_private=True)
        result = policy.validate("http://127.0.0.1:8000/")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is True
        assert result[1] == "OK"

    def test_returns_tuple_on_failure(self):
        policy = URLPolicy(allow_private=True)
        result = policy.validate("file:///etc/passwd")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is False
