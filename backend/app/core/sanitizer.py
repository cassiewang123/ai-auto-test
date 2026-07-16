"""敏感数据脱敏工具：用于 API 响应中屏蔽密码、密钥、Cookie 值等敏感信息."""
from __future__ import annotations


def mask_secret(value: str, visible: int = 4) -> str:
    """脱敏敏感字符串，仅显示前 visible 位。

    空值或长度不超过 visible 时返回 "****"。
    """
    if not value or len(value) <= visible:
        return "****"
    return value[:visible] + "****"


def sanitize_db_config(config: dict | None) -> dict | None:
    """脱敏数据库配置中的密码。

    将 password 替换为 "****"，并新增 has_password 布尔标记。
    """
    if config is None:
        return None
    sanitized = {**config}
    if sanitized.get("password"):
        sanitized["password"] = "****"
        sanitized["has_password"] = True
    else:
        sanitized.pop("password", None)
        sanitized["has_password"] = False
    return sanitized


def sanitize_cookies(cookies: list[dict] | None) -> list[dict]:
    """Replace Cookie values with a fixed mask and a presence marker."""
    if not cookies:
        return []
    sanitized: list[dict] = []
    for cookie in cookies:
        item = {**cookie}
        has_value = bool(item.get("value"))
        item.pop("value", None)
        item["value"] = "****" if has_value else ""
        item["has_value"] = has_value
        sanitized.append(item)
    return sanitized
